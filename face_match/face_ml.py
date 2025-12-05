# face_match/face_ml.py
import cv2
import os
import numpy as np
import face_recognition as fr
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from model.database import get_database
from connection.validate_officekit import Validate
import uuid
# This is the class we created earlier
from .faiss_manager import FaceIndexManager

WORKING_HOURES = 9
WORKING_SECONDS = 9 * 60 * 60
EXCEPTION_SECONDS = 300
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
uploads_path = os.path.join(BASE_DIR, "uploads")
os.makedirs(uploads_path, exist_ok=True)


def is_user_in_radius(branch_lat, branch_lng, user_lat, user_lng, radius_meters):
    from geopy.distance import geodesic
    branch = (branch_lat, branch_lng)
    user = (user_lat, user_lng)
    distance = geodesic(branch, user).meters
    return distance <= radius_meters, distance


def validate_face_image(image):
    h, w = image.shape[:2]
    if h < 480 or w < 480:
        return False, "Image resolution too low. Minimum required is 480x480.", None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    blur_score = cv2.Laplacian(gray_eq, cv2.CV_64F).var()

    if blur_score < 60:
        return False, f"Image is blurry (score: {blur_score:.2f}).", None

    brightness = np.mean(gray)
    if brightness < 60:
        return False, "Image too dark. Increase lighting.", None
    if brightness > 200:
        return False, "Image too bright. Reduce lighting.", None

    edges = cv2.Canny(gray, 30, 100)

    edge_pixels = np.sum(edges > 0)
    total_pixels = gray.size

    edge_ratio = edge_pixels / total_pixels

    if edge_ratio < 0.005:
        return False, "Background too bright or washed out.", None

    if edge_ratio > 0.30:
        return False, "Background too noisy or cluttered.", None

    small = cv2.resize(image, (0, 0), fx=0.75, fy=0.75)
    face_locations = fr.face_locations(small)

    if not face_locations:
        return False, "No face detected.", None

    if len(face_locations) > 1:
        return False, "Multiple faces detected.", None

    top, right, bottom, left = [x * 2 for x in face_locations[0]]

    face_w = right - left
    face_h = bottom - top

    if face_w < 150 or face_h < 150:
        return False, "Face too small. Move closer to the camera.", None

    face_crop = image[top:bottom, left:right]
    face_gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

    mouth_start = int(face_gray.shape[0] * 0.60)
    mouth_end = int(face_gray.shape[0] * 0.90)

    mouth_region = face_gray[mouth_start:mouth_end, :]

    if mouth_region.size == 0 or mouth_region.shape[0] < 10:
        return False, "Unable to detect mouth region. Adjust your face.", None
    mouth_edges = cv2.Canny(mouth_region, 20, 60)
    edge_ratio_mouth = np.sum(mouth_edges > 0) / mouth_region.size

    if edge_ratio_mouth < 0.008:
        return False, "Face obstruction detected (mask/sunglasses/cap).", None

    MIN_FACE_SIZE = 90

    if face_w < MIN_FACE_SIZE or face_h < MIN_FACE_SIZE:
        return False, "Face too small or far. Please move closer to camera."

    aspect_ratio = face_w / face_h
    if aspect_ratio < 0.6 or aspect_ratio > 1.8:
        return False, "Face tilted too much. Look straight at camera."

    encodings = fr.face_encodings(
        small, face_locations, num_jitters=1)
    if not encodings:
        return False, "Face encoding failed"
    return True, face_locations, encodings


class FaceAttendance:
    def __init__(self):
        pass

    def compare_faces(self, base_img, company_code, latitude, longitude):
        try:
            # 1. Read and decode image
            file_bytes = np.frombuffer(base_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image is None:
                return False, "Invalid image format"

            ok, message, encodings = validate_face_image(image)

            if not ok:
                return False, message

            current_encoding = encodings[0]

            MAX_ALLOWED_DISTANCE = 0.45
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
            if branch_name:
                branch = db[f'branch_{company_code}'].find_one({
                    "compony_code": company_code,
                    "branch_name": branch_name
                })
                if branch and all(k in branch for k in ("latitude", "longitude", "radius")):
                    in_radius, dist = is_user_in_radius(
                        branch["latitude"], branch["longitude"],
                        latitude, longitude, branch["radius"]
                    )
                    if not in_radius:
                        return False, f"Outside allowed area ({dist:.1f}m away)"

            # 8. Log Attendance
            return self._log_attendance(company_code, employee, best["distance"])

        except Exception as e:
            print(f"[FaceAttendance] Error: {e}")
            from main import app
            app.logger.info(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False, "System error"

    def update_face(self, employee_code, branch, agency, add_img, company_code, fullname, existing_office_kit_user=None):
        try:
            file_bytes = np.frombuffer(add_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image is None:
                return False, "Invalid image format"
            ok, message, encodings = validate_face_image(image)
            if not ok:
                return False, message
            encoding = np.array(encodings, dtype=np.float32)
            db = get_database(company_code)
            collection = db[f"encodings_{company_code}"]

            collection.create_index("employee_code", unique=True)
            cashe = FaceIndexManager(company_code)
            # Upsert the encoding in the database
            result = cashe.search(encoding, k=1, threshold=0.4)
            if result:
                print("This face already exists in the database.")
                return False, "This face already exists in the database."
            data = {
                "company_code": company_code,
                "employee_code": employee_code,
                "branch": branch,
                "agency": agency,
                "fullname": fullname,
                "existing_user_officekit": existing_office_kit_user,
                "encodings": encoding.tolist()
            }
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
            return True, "Face encoding updated successfully"

        except Exception as e:
            print(f"Error in update_face: {e}")
            return False, "System error during face update"

    def edit_user_details(self, employee_code, emp_face, compony_code, existing_officekit_user=None):
        try:
            db = get_database(compony_code)
            users = db["users"]

            update_data = {}
            if emp_face:
                file_bytes = np.frombuffer(emp_face.read(), np.uint8)
                image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

                if image is None:
                    return False, "Invalid image format"

                resized_image = cv2.resize(image, (0, 0), fx=0.75, fy=0.75)
                locations = fr.face_locations(resized_image)

                if not locations:
                    return False, "No faces found in the image"

                encodings = fr.face_encodings(resized_image, locations)

                if not encodings:
                    return False, "Could not generate face encoding"

                encoding = encodings[0]

                enc_collection = db[f"encodings_{compony_code}"]
                enc_collection.create_index("employee_code", unique=True)

                cache = FaceIndexManager(compony_code)

                # Check duplicate face
                result = cache.search(encoding, k=1, threshold=0.4)
                if result:
                    return False, "This face already exists in the database."

                enc_collection.update_one(
                    {"employee_code": employee_code, "company_code": compony_code},
                    {"$set": {"encodings": encoding.tolist()}},
                    upsert=True
                )

                cache.rebuild_index()

                update_data["face_updated"] = True

            return True, "User details updated successfully"

        except Exception as e:
            print(f"Error in edit_user_details: {e}")
            return False, "System error while updating user"

    def _log_attendance(self, company_code: str, employee: dict, distance: float):
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        db = get_database(company_code)
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

        # Validate & log to OfficeKit
        validate = Validate(company_code, employee["employee_code"])
        valid, user_details = validate.validate_employee()
        if user_details:
            validate.insert_log(direction)

        return True, {
            "fullname": employee["fullname"],
            "employee_code": employee["employee_code"],
            "direction": direction,
            "confidence_distance": round(distance, 4),
            "message": "Attendance marked successfully"
        }
