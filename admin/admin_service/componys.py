import re
from model.database import get_database
from datetime import datetime, timedelta
from model.database import exclude
from utility.settings import Settings
from model.compony_model import ComponyModel
from connection.officekit_onboarding import OnboardingOfficekit

def list_componys(company_id=None):
    client = get_database()  # this returns a MongoClient instance

    # Fetch all DB names except excluded ones
    all_dbs = client.list_database_names()
    companies_dbs = [db_name for db_name in all_dbs if db_name not in exclude]

    result = []

    for db_name in companies_dbs:
        db = client[db_name]  # do NOT overwrite the client
        collection = db.get_collection("compony_details")

        # Fetch specific company OR all companies
        if company_id:
            docs = list(collection.find(
                {"compony_code": str(company_id)}, {"_id": 0}))
        else:
            docs = list(collection.find({}, {"_id": 0}))

        # Add default values
        for doc in docs:
            doc["status"] = doc.get("status", "pending")
            doc["compony_code"] = str(doc.get("compony_code"))
            # helpful for knowing which company DB it came from
            doc["db_name"] = db_name
            result.append(doc)

    return result


def update_client_status(compony_code, status):
    client = get_database()  # MongoClient

    all_dbs = client.list_database_names()
    companies_dbs = [db_name for db_name in all_dbs if db_name not in exclude]

    updated_user = None
    target_db_name = None

    # Find the company DB that contains this company_code
    for db_name in companies_dbs:
        db = client[db_name]
        collection = db.get_collection("compony_details")

        # Check if the company exists in this DB
        user_details = collection.find_one({"compony_code": str(compony_code)})
        if user_details:
            # Update status
            target_db_name = db_name
            collection.update_one(
                {"compony_code": str(compony_code)},
                {"$set": {"status": status}},
                upsert=True
            )
            # Refresh after update
            updated_user = collection.find_one(
                {"compony_code": str(compony_code)})
            break

    # If not found in any DB
    if not updated_user:
        return {"error": "Company code not found"}
    

    if status == "rejected" and target_db_name:
        client.drop_database(target_db_name)
        return {
            "status": "rejected",
            "message": f"Database '{target_db_name}' deleted successfully"
        }

    # Send email
    to_email = updated_user.get("email")
    password = updated_user.get("password")
    compony_url = updated_user.get("compony_url", "")

    from helper.trigger_mail import send_mail_with_template
    send_mail_with_template(
        to_email,
        to_email,
        password,
        str(compony_code),
        compony_url
    )

    return True


import base64
import glob
import os

def fech_client_details(compony_code, limit=10, offset=0, date=None):
    client = get_database(compony_code)
    collection = client.get_collection(f"encodings_{compony_code}")

    attendance_map = {}

    if date:
        try:
            year_month = date[:7]
            att_coll_name = f"attandance_{compony_code}_{year_month}"

            att_coll = client[att_coll_name]

            search_date = datetime.strptime(date, "%Y-%m-%d")

            att_records = list(
                att_coll.find(
                    {
                        "date": {
                            "$gte": search_date,
                            "$lt": search_date + timedelta(days=1)
                        }
                    },
                    {"_id": 0}
                )
            )

            attendance_map = {
                r["employee_id"]: r
                for r in att_records
                if "employee_id" in r
            }

        except Exception as e:
            print(f"Error fetching attendance: {e}")

    # query = {"is_delete": {"$ne": True}}
    query = {}

    if date:
        query["employee_code"] = {
            "$in": list(attendance_map.keys())
        }

    total_count = collection.count_documents(query)

    emp_details = list(
        collection.find(
            query,
            {
                "_id": 0,
                "encodings": 0,
                "existing_user_officekit": 0,
                "company_code": 0
            }
        )
        .skip(offset)
        .limit(limit)
    )

    # ----------------------------------
    # Load images only once
    # ----------------------------------

    image_map = {}

    try:
        upload_dir = "face_match/uploads"

        if os.path.exists(upload_dir):
            emp_codes_set = {str(emp.get("employee_code", "")).lower() for emp in emp_details if emp.get("employee_code")}
            
            for filename in os.listdir(upload_dir):
                # Filename format: user_{emp_code}_{time}_{random}_{name}_{company}.jpg
                if filename.startswith("user_"):
                    parts = filename.split('_')
                    if len(parts) >= 2:
                        file_emp_code = parts[1].lower()
                        if file_emp_code in emp_codes_set:
                            image_map[file_emp_code] = filename
                            emp_codes_set.remove(file_emp_code)
                if not emp_codes_set:
                    break

    except Exception as e:
        print(f"Image loading error: {e}")

    # ----------------------------------
    # OfficeKit
    # ----------------------------------

    office_kit = OnboardingOfficekit(compony_code)

    branch_cache = {}
    agency_cache = {}

    # ----------------------------------
    # Employee Processing
    # ----------------------------------

    for emp in emp_details:

        emp_code = str(
            emp.get("employee_code", "")
        ).lower()

        emp["image"] = image_map.get(emp_code)

        if date:
            emp["attendance"] = attendance_map.get(
                emp.get("employee_code"),
                {}
            )

        branch = emp.get("branch")

        if branch and (
            isinstance(branch, int)
            or str(branch).isdigit()
        ):

            branch_key = str(branch)

            if branch_key not in branch_cache:

                try:
                    branch_data = office_kit.get_branch(
                        search=branch
                    )

                    if (
                        branch_data
                        and branch_data.get("data")
                    ):
                        branch_cache[branch_key] = (
                            branch_data["data"][0]["branch_name"]
                        )
                    else:
                        branch_cache[branch_key] = branch

                except Exception:
                    branch_cache[branch_key] = branch

            emp["branch"] = branch_cache[branch_key]

        # ------------------------------
        # Agency
        # ------------------------------

        agency = emp.get("agency")

        if agency and (
            isinstance(agency, int)
            or str(agency).isdigit()
        ):

            agency_key = str(agency)

            if agency_key not in agency_cache:

                try:
                    agency_data = office_kit.get_agency(
                        agency
                    )

                    if agency_data:
                        agency_cache[agency_key] = (
                            agency_data[0]["agent_name"]
                        )
                    else:
                        agency_cache[agency_key] = agency

                except Exception:
                    agency_cache[agency_key] = agency

            emp["agency"] = agency_cache[agency_key]

        # ------------------------------
        # Fallback: if still unresolved (missing, or a raw ID a prior lookup
        # above couldn't resolve), pull the employee's real branch/agency
        # straight from OfficeKit via their entity assignment.
        # ------------------------------
        branch_unresolved = _is_unresolved(emp.get("branch"))
        agency_unresolved = _is_unresolved(emp.get("agency"))
        if (branch_unresolved or agency_unresolved) and office_kit.conn and emp.get("employee_code"):
            try:
                org = office_kit.get_employee_org(emp.get("employee_code"))
            except Exception:
                org = None
            if org:
                if branch_unresolved and org.get("BranchName"):
                    emp["branch"] = org["BranchName"]
                if agency_unresolved and org.get("AgencyName"):
                    emp["agency"] = org["AgencyName"]

    return {
        "data": emp_details,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }

from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_branch_ids(compony_code, search_val):
    office_kit = OnboardingOfficekit(compony_code)
    if not office_kit.conn:
        return None
    branch_resp = office_kit.get_branch(search=search_val, limit=100)
    if branch_resp and branch_resp.get("data"):
        return [b["_id"] for b in branch_resp["data"]]
    return []

@lru_cache(maxsize=128)
def get_cached_agency_ids(compony_code, search_val):
    office_kit = OnboardingOfficekit(compony_code)
    if not office_kit.conn:
        return None
    agency_resp = office_kit.get_agency(search=search_val)
    if agency_resp:
        return [a["_id"] for a in agency_resp]
    return []

def fech_client_details_search(compony_code, search, limit=10, offset=0, date=None, branch=None, agency=None, name=None, employee_code=None):
    client = get_database(compony_code)  # MongoClient
    collection = client.get_collection(f"encodings_{compony_code}")
    
    attendance_map = {}
    if date:
        try:
            year_month = date[:7]
            att_coll_name = f"attandance_{compony_code}_{year_month}"
            if att_coll_name in client.list_collection_names():
                att_coll = client[att_coll_name]
                search_date = datetime.strptime(date, "%Y-%m-%d")
                att_records = list(att_coll.find({
                    "date": {"$gte": search_date, "$lt": search_date + timedelta(days=1)}
                }, {"_id": 0}))
                attendance_map = {r['employee_id']: r for r in att_records}
        except Exception as e:
            print(f"Error fetching attendance in search: {e}")

    query_parts = [{"is_delete": {"$ne": True}}]
    
    
    office_kit = OnboardingOfficekit(compony_code)
    
    if branch:
        if not (isinstance(branch, int) or re.match(r'^\d+$', str(branch))):
            branch_ids = get_cached_branch_ids(compony_code, branch)
            if branch_ids is not None:
                if branch_ids:
                    query_parts.append({"branch": {"$in": branch_ids + [str(b) for b in branch_ids]}})
                else:
                    query_parts.append({"branch": -1}) # no match
            else:
                query_parts.append({"branch": {"$regex": branch, "$options": "i"}})
        else:
            query_parts.append({"branch": branch})
            
    if agency:
        if not (isinstance(agency, int) or re.match(r'^\d+$', str(agency))):
            agency_ids = get_cached_agency_ids(compony_code, agency)
            if agency_ids is not None:
                if agency_ids:
                    query_parts.append({"agency": {"$in": agency_ids + [str(a) for a in agency_ids]}})
                else:
                    query_parts.append({"agency": -1}) # no match
            else:
                query_parts.append({"agency": {"$regex": agency, "$options": "i"}})
        else:
            query_parts.append({"agency": agency})
    if name:
        query_parts.append({"fullname": {"$regex": name, "$options": "i"}})
    if employee_code:
        query_parts.append({"employee_code": {"$regex": employee_code, "$options": "i"}})
        
    if date:
        att_ids = list(attendance_map.keys())
        query_parts.append({"employee_code": {"$in": att_ids}})
        
    query = {}
    if query_parts:
        if len(query_parts) == 1:
            query = query_parts[0]
        else:
            query = {"$and": query_parts}
            
    total_count = collection.count_documents(query)
    cursor = collection.find(query, {"_id": 0, "encodings": 0, "existing_user_officekit":0, "company_code":0}).skip(offset).limit(limit)
    
    emp_details = list(cursor)
    office_kit = OnboardingOfficekit(compony_code)

    branch_cache = {}
    agency_cache = {}

    # Pre-fetch images mapping for search results
    image_map = {}
    try:
        upload_dir = "face_match/uploads"
        if os.path.exists(upload_dir):
            emp_codes_set = {str(emp.get("employee_code", "")).lower() for emp in emp_details if emp.get("employee_code")}
            for filename in os.listdir(upload_dir):
                if filename.startswith("user_"):
                    parts = filename.split('_')
                    if len(parts) >= 2:
                        file_emp_code = parts[1].lower()
                        if file_emp_code in emp_codes_set:
                            image_map[file_emp_code] = filename
                            emp_codes_set.remove(file_emp_code)
                if not emp_codes_set:
                    break
    except Exception as e:
        pass
        
    for emp in emp_details:
        emp_code = str(emp.get('employee_code', '')).lower()
        emp["image"] = image_map.get(emp_code)
        
        # Attach attendance info if date was provided
        if date:
            emp["attendance"] = attendance_map.get(emp_code, {})

        branch = emp.get('branch')
        if branch and (isinstance(branch, int) or re.match(r'^\d+$', str(branch))):
            branch_key = str(branch)
            if branch_key not in branch_cache:
                try:
                    branch_data = office_kit.get_branch(search=branch)
                    if branch_data and branch_data.get('data'):
                        branch_cache[branch_key] = branch_data['data'][0]['branch_name']
                    else:
                        branch_cache[branch_key] = branch
                except Exception:
                    branch_cache[branch_key] = branch
            emp['branch'] = branch_cache[branch_key]

        emp_agency = emp.get('agency')
        if emp_agency and (isinstance(emp_agency, int) or re.match(r'^\d+$', str(emp_agency))):
            agency_key = str(emp_agency)
            if agency_key not in agency_cache:
                try:
                    agency_data = office_kit.get_agency(emp_agency)
                    if agency_data:
                        agency_cache[agency_key] = agency_data[0]['agent_name']
                    else:
                        agency_cache[agency_key] = emp_agency
                except Exception:
                    agency_cache[agency_key] = emp_agency
            emp['agency'] = agency_cache[agency_key]

        # Fallback: if still unresolved (missing, or a raw ID the lookups
        # above couldn't resolve), pull the employee's real branch/agency
        # straight from OfficeKit via their entity assignment.
        branch_unresolved = _is_unresolved(emp.get("branch"))
        agency_unresolved = _is_unresolved(emp.get("agency"))
        if (branch_unresolved or agency_unresolved) and office_kit.conn and emp.get("employee_code"):
            try:
                org = office_kit.get_employee_org(emp.get("employee_code"))
            except Exception:
                org = None
            if org:
                if branch_unresolved and org.get("BranchName"):
                    emp["branch"] = org["BranchName"]
                if agency_unresolved and org.get("AgencyName"):
                    emp["agency"] = org["AgencyName"]

    return {
        "data": emp_details,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "search": search
    }


def set_portal_credentials(compony_code, admin_username, admin_password):
    """Set/reset the dedicated admin-portal login for one company (separate from their app login)."""
    client = get_database()
    for db_name in client.list_database_names():
        if db_name in exclude or db_name == compony_code:
            continue
        existing = client[db_name].get_collection("compony_details").find_one(
            {"admin_username": admin_username}
        )
        if existing:
            return {"error": "That admin_username is already taken by another company"}

    db = get_database(compony_code)
    collection = db.get_collection("compony_details")
    result = collection.update_one(
        {"compony_code": str(compony_code)},
        {"$set": {"admin_username": admin_username, "admin_password": admin_password}}
    )
    if result.matched_count == 0:
        return {"error": "Company not found"}
    return {"message": "success"}


def _is_unresolved(value):
    """True if a branch/agency value is missing, or is still a raw numeric ID
    that a prior OfficeKit lookup failed to resolve to a name."""
    if not value:
        return True
    return isinstance(value, int) or (isinstance(value, str) and value.isdigit())


def _delete_employee_from_officekit(compony_code, employee_code):
    """Best-effort hard delete of an employee from every Officekit table
    add_user() ever inserts into (children before parents, reverse insert
    order), plus attendance staging. Silently no-ops if this company has no
    Officekit connection configured."""
    from connection.officekit_onboarding import OnboardingOfficekit

    office_kit = OnboardingOfficekit(compony_code)
    if not office_kit.conn:
        return

    try:
        cursor = office_kit.conn.cursor(as_dict=True)

        cursor.execute("SELECT Emp_ID FROM HR_EMP_MASTER WHERE Emp_Code = %s", (employee_code,))
        emp_row = cursor.fetchone()
        emp_id = emp_row["Emp_ID"] if emp_row else None

        cursor.execute("SELECT UserID FROM ADM_User_Master WHERE UserName = %s", (employee_code,))
        user_row = cursor.fetchone()
        user_id = user_row["UserID"] if user_row else None

        cursor.execute("DELETE FROM ATTENDANCELOG_STAGING WHERE UserId = %s", (employee_code,))

        if emp_id is not None:
            cursor.execute("DELETE FROM SHIFT_MASTER_ACCESS WHERE EmployeeID = %s", (emp_id,))
            cursor.execute("DELETE FROM ATTENDANCEPOLICY_MASTER_ACCESS WHERE EmployeeID = %s", (emp_id,))
            cursor.execute("DELETE FROM BIOMETRICS_DTL WHERE EmployeeID = %s", (emp_id,))
            cursor.execute("DELETE FROM HR_EMP_ADDRESS WHERE Emp_Id = %s", (emp_id,))
            cursor.execute("DELETE FROM HR_EMP_IMAGES WHERE emp_id = %s", (emp_id,))
            cursor.execute("DELETE FROM HR_EMPLOYEE_USER_RELATION WHERE Emp_Id = %s", (emp_id,))

        if user_id is not None:
            cursor.execute("DELETE FROM ADM_UserRoleMaster WHERE User_Id = %s", (user_id,))
            cursor.execute("DELETE FROM ADM_User_Master WHERE UserID = %s", (user_id,))

        cursor.execute("DELETE FROM HR_EMP_MASTER WHERE Emp_Code = %s", (employee_code,))

        office_kit.conn.commit()
    except Exception as e:
        office_kit.conn.rollback()
        print(f"OfficeKit deletion failed for {employee_code} ({compony_code}): {e}")


def force_delete_employee(compony_code, employee_code):
    if not compony_code or not employee_code:
        return {"error": "compony_code and employee_code are required"}

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")

    result = collection.delete_one({"employee_code": employee_code})
    if result.deleted_count == 0:
        return {"error": "Employee not found"}

    _delete_employee_from_officekit(compony_code, employee_code)

    from face_match.faiss_manager import FaceIndexManager
    FaceIndexManager(compony_code).rebuild_index()

    return {"message": "success"}


def delete_employee_facekit_only(compony_code, employee_code):
    """Delete an employee from Facekit's own database only - Officekit (if
    this company has it wired up) is left untouched. See force_delete_employee
    for the variant that also removes the employee from Officekit."""
    if not compony_code or not employee_code:
        return {"error": "compony_code and employee_code are required"}

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")

    result = collection.delete_one({"employee_code": employee_code})
    if result.deleted_count == 0:
        return {"error": "Employee not found"}

    from face_match.faiss_manager import FaceIndexManager
    FaceIndexManager(compony_code).rebuild_index()

    return {"message": "success"}


def switch_employee_branch(compony_code, employee_code, branch_id):
    """Change an employee's branch. Always updates the local Mongo record;
    if this company has Officekit integration turned on, also moves the
    employee to the matching org-entity in Officekit first, so both sides
    end up pointing at the same branch (and Mongo's `branch` value ends up as
    Officekit's resolved id, not just whatever the caller passed in)."""
    if not compony_code or not employee_code or branch_id is None:
        return {"error": "compony_code, employee_code and branch_id are required"}

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")
    if not collection.find_one({"employee_code": employee_code}):
        return {"error": "Employee not found"}

    officekit_result = None
    if Settings.get_setting(compony_code, "Office Kit Integration"):
        office_kit = OnboardingOfficekit(compony_code)
        if office_kit.conn:
            try:
                officekit_result = office_kit.switch_branch(employee_code, branch_id)
            except Exception as e:
                return {"error": f"Officekit branch switch failed: {e}"}

    mongo_branch_value = officekit_result["branch_id"] if officekit_result else branch_id
    collection.update_one(
        {"employee_code": employee_code},
        {"$set": {"branch": mongo_branch_value}}
    )

    return {"message": "success", "officekit": officekit_result}


def switch_employee_agency(compony_code, employee_code, agency_id):
    """Change an employee's agency, same pattern as switch_employee_branch -
    Officekit first (if integrated), then Mongo reflects whatever Officekit
    resolved."""
    if not compony_code or not employee_code or agency_id is None:
        return {"error": "compony_code, employee_code and agency_id are required"}

    db = get_database(compony_code)
    collection = db.get_collection(f"encodings_{compony_code}")
    if not collection.find_one({"employee_code": employee_code}):
        return {"error": "Employee not found"}

    officekit_result = None
    if Settings.get_setting(compony_code, "Office Kit Integration"):
        office_kit = OnboardingOfficekit(compony_code)
        if office_kit.conn:
            try:
                officekit_result = office_kit.switch_agency(employee_code, agency_id)
            except Exception as e:
                return {"error": f"Officekit agency switch failed: {e}"}

    mongo_agency_value = officekit_result["agency_name"] if officekit_result else agency_id
    collection.update_one(
        {"employee_code": employee_code},
        {"$set": {"agency": mongo_agency_value}}
    )

    return {"message": "success", "officekit": officekit_result}


def create_company(data):
    if not data:
        return jsonify({"error": "No JSON body received"}), 400

    compony_name = data.get("compony_name")
    _name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    mobile_no = data.get("mobile_no")
    emp_count = data.get("emp_count")
    client = data.get("client")
    if not all([compony_name, _name, email, password, mobile_no, emp_count]):
        return jsonify({"error": "Missing required fields"})

    
    componyCode = ComponyModel(client)
    message, company_code = componyCode._set(
        compony_name, _name, email, password, mobile_no, emp_count, client)
        
    if message == "faild":
        return message
    return message