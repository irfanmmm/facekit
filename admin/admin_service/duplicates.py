import os

from model.database import get_database
from model.user_model import UserModel

UPLOAD_DIR = "face_match/uploads"


def _find_employee_photo(employee_code):
    """Employee photos aren't stored as a field on the Mongo doc — they live on
    disk as user_{employee_code}_..._.jpg and have to be found by prefix match."""
    if not employee_code or not os.path.exists(UPLOAD_DIR):
        return None

    prefix = f"user_{str(employee_code).lower()}_"
    for filename in os.listdir(UPLOAD_DIR):
        if filename.lower().startswith(prefix):
            return filename
    return None


# The face-matching system treats anything under this distance as the same
# person during real attendance punches — only pairs at least this close are
# worth surfacing as an actual duplicate.
REAL_MATCH_THRESHOLD = 0.6

# An employee whose record shows up across this many different flagged pairs
# almost always means their own encoding is bad/generic (e.g. no photo ever
# attached), not that they're a duplicate of everyone they're paired with.
# Any pair involving such a record is noise, not a real candidate to merge.
HUB_APPEARANCE_LIMIT = 3

# A stricter bar for actually calling out a record as "bad" in its own right.
# A genuinely broken encoding shows up dozens of times; an innocent employee
# who simply happens to match every broken record in the company once each
# will land right at HUB_APPEARANCE_LIMIT too — this keeps that collateral
# case out of the bad-records list while still excluding it from duplicates.
BAD_RECORD_DISPLAY_LIMIT = HUB_APPEARANCE_LIMIT * 2


def _detect_candidates(compony_code, threshold):
    """Run the raw face-similarity scan and return every flagged pair (before
    any filtering) plus how many different pairs each employee_code shows up
    in — the shared building block behind both the clean duplicate list and
    the bad-face-record report."""
    raw = UserModel(compony_code).find_duplicate_faces(compony_code, threshold)

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")

    seen_pairs = set()
    candidates = []

    for emp_code, matches in raw.items():
        for match in matches:
            other_code = match["matched_employee"]
            if other_code == emp_code:
                continue

            pair_key = tuple(sorted([emp_code, other_code]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            docs = {
                d["employee_code"]: d
                for d in collection.find(
                    {"employee_code": {"$in": [emp_code, other_code]}},
                    {"encodings": 0, "encodings_v2": 0}
                )
            }
            doc_a = docs.get(emp_code)
            doc_b = docs.get(other_code)
            if not doc_a or not doc_b:
                continue

            candidates.append({
                "distance": match["distance"],
                "employees": [_summarize_employee(doc_a), _summarize_employee(doc_b)]
            })

    appearance_counts = {}
    for candidate in candidates:
        for emp in candidate["employees"]:
            appearance_counts[emp["employee_code"]] = appearance_counts.get(emp["employee_code"], 0) + 1

    return candidates, appearance_counts


def list_duplicate_faces(compony_code, threshold=0.85):
    """Detect genuinely likely duplicate-face pairs for a company and return them
    with enough employee detail (name, photo, branch/agency) for an admin to
    review. Loose/noisy candidates — low-confidence matches and pairs involving
    a "hub" record with a bad encoding — are filtered out entirely rather than
    shown, so only real duplicates worth merging make it into the list."""
    if not compony_code:
        return {"error": "compony_code is required"}

    candidates, appearance_counts = _detect_candidates(compony_code, threshold)

    pairs = [
        candidate for candidate in candidates
        if candidate["distance"] < REAL_MATCH_THRESHOLD
        and all(appearance_counts[emp["employee_code"]] < HUB_APPEARANCE_LIMIT for emp in candidate["employees"])
    ]

    pairs.sort(key=lambda p: p["distance"])
    return {"pairs": pairs}


def list_bad_face_records(compony_code, threshold=0.85):
    """Employees whose record shows up across many different flagged pairs
    almost always have a bad/corrupt/generic face encoding rather than being a
    real duplicate of everyone they match — list_duplicate_faces filters these
    out entirely, so surface them here instead for an admin to review and fix
    (e.g. re-capture their photo) rather than letting them silently disappear."""
    if not compony_code:
        return {"error": "compony_code is required"}

    candidates, appearance_counts = _detect_candidates(compony_code, threshold)

    bad_codes = {code for code, count in appearance_counts.items() if count >= BAD_RECORD_DISPLAY_LIMIT}
    if not bad_codes:
        return {"employees": []}

    employees_by_code = {}
    for candidate in candidates:
        for emp in candidate["employees"]:
            if emp["employee_code"] in bad_codes:
                employees_by_code[emp["employee_code"]] = emp

    employees = list(employees_by_code.values())
    for emp in employees:
        emp["match_count"] = appearance_counts[emp["employee_code"]]

    employees.sort(key=lambda e: e["match_count"], reverse=True)
    return {"employees": employees}


def _summarize_employee(doc):
    return {
        "employee_code": doc.get("employee_code"),
        "fullname": doc.get("fullname"),
        "branch": doc.get("branch"),
        "agency": doc.get("agency"),
        "image": _find_employee_photo(doc.get("employee_code")),
        "created_at": doc["_id"].generation_time.isoformat() if doc.get("_id") else None,
    }


def _transfer_employee_photo(old_employee_code, new_employee_code):
    """Rename the old employee's uploaded photo file so it's found under the new
    employee_code instead, replacing whatever photo the new code already had."""
    if not os.path.exists(UPLOAD_DIR):
        return

    old_prefix = f"user_{str(old_employee_code).lower()}_"
    new_prefix = f"user_{str(new_employee_code).lower()}_"
    old_file = None
    stale_files = []

    for filename in os.listdir(UPLOAD_DIR):
        lower_name = filename.lower()
        if lower_name.startswith(old_prefix):
            old_file = filename
        elif lower_name.startswith(new_prefix):
            stale_files.append(filename)

    for filename in stale_files:
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename))
        except Exception as e:
            print(f"Failed removing stale photo {filename}: {e}")

    if old_file:
        parts = old_file.split("_")
        if len(parts) >= 2:
            parts[1] = new_employee_code
            new_filename = "_".join(parts)
            try:
                os.rename(os.path.join(UPLOAD_DIR, old_file), os.path.join(UPLOAD_DIR, new_filename))
            except Exception as e:
                print(f"Failed renaming photo {old_file} -> {new_filename}: {e}")


def merge_duplicate_employees(compony_code, primary_employee_code, duplicate_employee_code):
    """Merge a duplicate employee into the chosen primary: the duplicate's face
    is copied onto the primary, all attendance history (Mongo + OfficeKit) is
    reassigned to the primary, then the duplicate is permanently removed from
    both Mongo and OfficeKit."""
    if not all([compony_code, primary_employee_code, duplicate_employee_code]):
        return {"error": "compony_code, primary_employee_code and duplicate_employee_code are required"}
    if primary_employee_code == duplicate_employee_code:
        return {"error": "primary and duplicate employee codes must differ"}

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")

    primary_doc = collection.find_one({"employee_code": primary_employee_code})
    duplicate_doc = collection.find_one({"employee_code": duplicate_employee_code})

    if not primary_doc:
        return {"error": "Primary employee not found"}
    if not duplicate_doc:
        return {"error": "Duplicate employee not found"}

    update_data = {}
    if duplicate_doc.get("encodings"):
        update_data["encodings"] = duplicate_doc["encodings"]
    if duplicate_doc.get("encodings_v2"):
        update_data["encodings_v2"] = duplicate_doc["encodings_v2"]
    if update_data:
        collection.update_one({"_id": primary_doc["_id"]}, {"$set": update_data})

    _transfer_employee_photo(duplicate_employee_code, primary_employee_code)

    # Migrate MongoDB attendance history onto the primary employee code.
    for coll_name in db.list_collection_names():
        if coll_name.startswith(f"attandance_{compony_code}"):
            db[coll_name].update_many(
                {"employee_id": duplicate_employee_code},
                {"$set": {"employee_id": primary_employee_code}}
            )

    # Migrate OfficeKit attendance and remove the duplicate's HR record.
    from connection.officekit_onboarding import OnboardingOfficekit
    office_kit = OnboardingOfficekit(compony_code)
    if office_kit.conn:
        try:
            cursor = office_kit.conn.cursor()
            cursor.execute(
                "UPDATE ATTENDANCELOG_STAGING SET UserId = %s WHERE UserId = %s",
                (primary_employee_code, duplicate_employee_code)
            )
            cursor.execute(
                "DELETE FROM HR_EMP_MASTER WHERE Emp_Code = %s",
                (duplicate_employee_code,)
            )
            office_kit.conn.commit()
        except Exception as e:
            office_kit.conn.rollback()
            print(f"OfficeKit merge cleanup failed for {duplicate_employee_code} ({compony_code}): {e}")

    collection.delete_one({"_id": duplicate_doc["_id"]})

    from face_match.faiss_manager import FaceIndexManager
    FaceIndexManager(compony_code).rebuild_index()

    return {"message": "success"}
