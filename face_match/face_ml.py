import logging
import cv2
import os
import numpy as np
import face_recognition as fr
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from functools import lru_cache
from model.database import get_database
from connection.validate_officekit import Validate
from utility.settings import Settings
import uuid
from geopy.distance import geodesic
from .faiss_manager import FaceIndexManager
import time
import base64
from connection.officekit_punching import OfficeKitPunching
from connection.officekit_onboarding import OnboardingOfficekit
from model.compony_model import ComponyModel
WORKING_HOURES = 9
WORKING_SECONDS = 9 * 60 * 60
EXCEPTION_SECONDS = 300
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
uploads_path = os.path.join(BASE_DIR, "uploads")
os.makedirs(uploads_path, exist_ok=True)

log_path = "logs/compare(ml)facekit.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logger = logging.getLogger("face_ml")


def is_user_in_radius(branch_lat, branch_lng, user_lat, user_lng, radius_meters):
    branch = (branch_lat, branch_lng)
    user = (user_lat, user_lng)
    distance = geodesic(branch, user).meters
    return distance <= radius_meters, distance


def save_employee_image(image):
    filename = f"{uuid.uuid4().hex}.jpg"
    file_path = os.path.join(uploads_path, filename)
    logger.info(file_path)
    cv2.imwrite(file_path, image)
    return


def validate_face_image(image):
    h, w = image.shape[:2]
    if h < 320 or w < 320:
        return False, "Image resolution too low. Minimum required is 320x320.", None

    # Resize large images to maximum 800x800 to significantly boost face_recognition speed
    max_dim = 800
    if h > max_dim or w > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = image.shape[:2] # Update dimensions after resize

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    blur_score = cv2.Laplacian(gray_eq, cv2.CV_64F).var()

    if blur_score < 5:
        return False, f"Image is blurry (score: {blur_score:.2f}).", None

    brightness = np.mean(gray)
    if brightness < 20:
        return False, "Image too dark. Increase lighting.", None
    if brightness > 250:
        return False, "Image too bright. Reduce lighting.", None

    face_locations = fr.face_locations(image)

    if not face_locations:
        return False, "No face detected.", None

    if len(face_locations) > 1:
        return False, "Multiple faces detected.", None

    top, right, bottom, left = [x * 2 for x in face_locations[0]]

    face_w = right - left
    face_h = bottom - top

    MIN_FACE_SIZE = 60

    if face_w < MIN_FACE_SIZE or face_h < MIN_FACE_SIZE:
        return False, "Face too small. Move closer to the camera.", None

    aspect_ratio = face_w / face_h
    if aspect_ratio < 0.5 or aspect_ratio > 2.0:
        return False, "Face tilted too much. Look straight at camera.", None

    encodings = fr.face_encodings(image, face_locations, num_jitters=1)
    if not encodings:
        return False, "Face encoding failed.", None

    return True, face_locations, encodings


@lru_cache(maxsize=128)
def _get_local_branch_cached(company_code, branch_name):
    db = get_database(company_code)
    return db[f'branch_{company_code}'].find_one({
        "compony_code": company_code,
        "branch_name": branch_name
    })


class FaceAttendance:
    def __init__(self):
        pass

    def compare_faces(self, base_img, company_code, latitude, longitude, officekit_user):
        try:
            try:
                img_bytes = base64.b64decode(base_img)
            except:
                return False, "invalid image"

            np_arr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if image is None:
                return "Invalid image"

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            ok, message, encodings = validate_face_image(image_rgb)

            if not ok:
                return False, message

            current_encoding = encodings[0]

            MAX_ALLOWED_DISTANCE = 0.40
            manager = FaceIndexManager(company_code)
            candidates = manager.search(
                current_encoding, k=10, threshold=MAX_ALLOWED_DISTANCE)

            if not candidates:
                return False, "No matching face found"

            # 6. Get best match
            best = min(candidates, key=lambda x: x["distance"])

            if best["distance"] > MAX_ALLOWED_DISTANCE:
                return False, f"Face not recognized (distance: {best['distance']:.3f})"

            employee = best["employee"]

            # 7. Geo-fencing check
            branch_name = employee.get("branch")
            db = get_database(company_code)

            if Settings.get_setting(company_code, "Location Tracking"):
                if branch_name:
                    if officekit_user:
                        off = OfficeKitPunching(company_code)
                        branch = off.retreve_codinates(branch_name)
                    else:
                        branch = _get_local_branch_cached(
                            company_code, branch_name)
                    if branch and all(k in branch for k in ("latitude", "longitude", "radius")):
                        in_radius, dist = is_user_in_radius(
                            branch["latitude"], branch["longitude"], latitude, longitude, branch["radius"])
                        if not in_radius:
                            return False, f"Outside allowed area ({dist:.1f}m away)"

            # 8. Log Attendance
            return self._log_attendance(company_code, employee, best["distance"], db, officekit_user)

        except Exception as e:
            print(f"[FaceAttendance] Error: {e}")

            logger.info(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False, "System error"

    def update_face(self, branch, agency, add_img, company_code, fullname, gender, existing_office_kit_user=False, employeecode=None):
        try:
            try:
                img_bytes = base64.b64decode(add_img)
            except:
                return False, "invalid image"
            np_arr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if image is None:
                return "Invalid image"

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # generate new employee code
            compony = ComponyModel(compony_code=company_code)
            if not employeecode:
                employee_code = compony._generate_employee_code(company_code)
            else:
                # check existing employee code
                employee_code = employeecode.strip() if employeecode else employeecode
                if compony._check_employee_code(company_code, employee_code):
                    return False, "This employee already exists"
            filename = f"user_{employee_code}_{branch}_{agency}_{fullname}_{company_code}.jpg"
            filepath = os.path.join(uploads_path, filename)
            cv2.imwrite(filepath, image)

            ok, message, encodings = validate_face_image(image_rgb)

            if not ok:
                return False, message

            current_encoding = encodings[0]

            MAX_ALLOWED_DISTANCE = 0.40
            cashe = FaceIndexManager(company_code)
            candidates = cashe.search(
                current_encoding, k=10, threshold=MAX_ALLOWED_DISTANCE)

            if candidates:
                return False, "This face already exists in the database."

            encoding = np.array(current_encoding, dtype=np.float32)

            data = {
                "company_code": company_code,
                "employee_code": employee_code,
                "branch": branch,
                "agency": agency,
                "fullname": fullname,
                "existing_user_officekit": existing_office_kit_user,
                "encodings": encoding.tolist(),
                "created_date": datetime.now()
            }

            db = get_database(company_code)
            collection = db[f"encodings_{company_code}"]

            result = collection.insert_one(data)

            cashe.add_employee({
                "company_code": company_code,
                "employee_code": employee_code,
                "branch": branch,
                "agency": agency,
                "fullname": fullname,
                "existing_user_officekit": existing_office_kit_user,
                "encodings": encoding.tolist(),
                "_id": result.inserted_id
            })

            if Settings.get_setting(company_code, "Office Kit Onboarding"):
                add_user = OnboardingOfficekit(company_code)
                add_user.add_user(employee_code, branch,
                            agency, company_code, fullname, gender)
            return True, "success"

        except Exception as e:
            print(f"Error in update_face: {e}")
            logger.info(f"ERROR: {e}")
            return False, "System error during face update"

    def edit_employee_face(self, employee_code, emp_face, compony_code, existing_officekit_user=None):
        employee_code = employee_code.strip() if employee_code else employee_code
        try:
            try:
                img_bytes = base64.b64decode(emp_face)
            except:
                return False, "invalid image"

            np_arr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if image is None:
                return False, "Invalid image"

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            ok, message, encodings = validate_face_image(image_rgb)
            if not ok:
                return False, message

            if not encodings:
                return False, "Could not generate face encoding"

            current_encoding = encodings[0]
            cache = FaceIndexManager(compony_code)
            
            # Check for duplicates
            result = cache.search(current_encoding, k=1, threshold=0.40)
            if (isinstance(result, list) and len(result) > 0 and result[0].get("employee", {}).get("employee_code") == employee_code ):  
                return False, "This face already exists in the database."

            # Update Database Encodings
            encoding = np.array(current_encoding, dtype=np.float32)
            db = get_database(compony_code)
            enc_collection = db[f"encodings_{compony_code}"]
            enc_collection.update_one(
                {"employee_code": employee_code, "company_code": compony_code},
                {"$set": {"encodings": encoding.tolist()}},
            )

            # Background thread for Image Replacement and Index Rebuild
            import threading
            def _bg_replace_and_rebuild(emp_code, img, cache_obj):
                try:
                    import glob
                    pattern = os.path.join(uploads_path, f"user_{emp_code}*")
                    existing_files = glob.glob(pattern)
                    
                    if existing_files:
                        target_path = existing_files[0]
                    else:
                        target_path = os.path.join(uploads_path, f"user_{emp_code}.jpg")
                    
                    cv2.imwrite(target_path, img)
                    cache_obj.rebuild_index()
                except Exception as e:
                    print(f"Background update error: {e}")

            threading.Thread(target=_bg_replace_and_rebuild, args=(employee_code, image, cache)).start()

            return True, "User details updated successfully"

        except Exception as e:
            print(f"Error in edit_user_details: {e}")
            logger.info(f"ERROR: {e}")
            return False, "System error while updating user"

    def _log_attendance(self, company_code: str, employee: dict, distance: float, db, officekit_user=False, async_officekit=False):
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        collection_name = f"attandance_{company_code}_{now.strftime('%Y-%m')}"
        collection = db[collection_name]

        filter_query = {
            "employee_id": employee["employee_code"],
            "date": {"$gte": today_start, "$lt": tomorrow_start}
        }
        record = collection.find_one(filter_query)

        direction = "in"
        log_entry = {
            "direction": "in",
            "time": now,
            "confidence_distance": round(distance, 4)
        }

        if record and record.get("log_details"):
            last_log = record["log_details"][-1]
            if last_log.get("direction") == "in":
                direction = "out"
                duration = (now - last_log["time"]).total_seconds()
                log_entry["direction"] = "out"

                present = ""
                including_exception = max(duration - EXCEPTION_SECONDS, 0)
                if including_exception >= WORKING_SECONDS:
                    present = "P"
                collection.update_one(
                    filter_query,
                    {
                        "$set": {"present": present},
                        "$push": {"log_details": log_entry},
                        "$inc": {"total_working_time": duration}
                    }
                )
            else:
                collection.update_one(
                    filter_query,
                    {"$push": {"log_details": log_entry}}
                )
        elif record:
            # First check-in of the day
            _filter = {
                "employee_id": employee["employee_code"],
            }

            _updated_data = {
                "company_code": company_code,
                "fullname": employee["fullname"],
                "date": now,
                "present": "",
                "total_working_time": 0,
                "updated_at": datetime.utcnow()
            }

            collection.update_one(
                _filter,
                {
                    "$set": _updated_data,
                    "$push": {
                        "log_details": log_entry
                    }
                },
                upsert=True
            )
        else:
            collection.insert_one({
                "employee_id": employee["employee_code"],
                "fullname": employee["fullname"],
                "company_code": company_code,
                "date": now,
                "total_working_time": 0,
                "present": "",
                "log_details": [log_entry]
            })

        # if officekit_user:
        
        import threading
        def _bg_punch(dir_val, emp_code, comp_code):
            try:
                punching = OfficeKitPunching(comp_code)
                punching.punchin_punchout(dir_val, emp_code)
            except Exception as e:
                logger.error(f"Background Punching Error: {e}")
                
        t = threading.Thread(target=_bg_punch, args=(direction, employee["employee_code"], company_code))
        t.start()

        working_hours = OfficeKitPunching(company_code)
        duration = working_hours.retreve_working_hours(employee["employee_code"])

        return True, {
            "fullname": employee["fullname"],
            "employee_code": employee["employee_code"],
            "direction": direction,
            "working_time": duration,
            "confidence_distance": round(distance, 4),
            "message": "Attendance marked successfully"
        }
