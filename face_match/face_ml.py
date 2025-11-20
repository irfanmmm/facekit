# face_match/face_ml.py
import cv2
import numpy as np
import face_recognition as fr
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from model.database import get_database
from connection.validate_officekit import Validate
# This is the class we created earlier
from .faiss_manager import FaceIndexManager


def is_user_in_radius(branch_lat, branch_lng, user_lat, user_lng, radius_meters):
    from geopy.distance import geodesic
    branch = (branch_lat, branch_lng)
    user = (user_lat, user_lng)
    distance = geodesic(branch, user).meters
    return distance <= radius_meters, distance


class FaceAttendance:
    def __init__(self):
        pass

    def compare_faces(self, base_img, company_code, latitude, longitude, individual_login, officekit_user, user = None):
        try:
            # 1. Read and decode image
            file_bytes = np.frombuffer(base_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image is None:
                return False, "Invalid image format"

            # 2. Resize for speed
            small_image = cv2.resize(image, (0, 0), fx=0.5, fy=0.5)

            # 3. Detect face
            face_locations = fr.face_locations(small_image, model="hog")
            if not face_locations:
                return False, "No face detected"

            if len(face_locations) > 1:
                return False, "Multiple faces detected"

            # CORRECT way to get face bounding box
            top, right, bottom, left = face_locations[0]

            face_width = right - left
            face_height = bottom - top

            MIN_FACE_SIZE = 90  

            if face_width < MIN_FACE_SIZE or face_height < MIN_FACE_SIZE:
                return False, "Face too small or far. Please move closer to camera."

            aspect_ratio = face_width / face_height
            if aspect_ratio < 0.6 or aspect_ratio > 1.8:
                return False, "Face tilted too much. Look straight at camera."

            encodings = fr.face_encodings(
                small_image, face_locations, num_jitters=1)
            if not encodings:
                return False, "Face encoding failed"
            current_encoding = encodings[0]

            # adjust this value based on your accuracy requirements
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
            db = get_database()
            if branch_name:
                branch = db[f'branch_{company_code}'].find_one({
                    "company_code": company_code,
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
            import traceback
            traceback.print_exc()
            return False, "System error"

    def update_face(self, employee_code, branch, add_img, company_code, fullname, existing_office_kit_user=None):
        try:

            file_bytes = np.frombuffer(add_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if image is None:
                return False

            # More reasonable resize - keep more detail for better encoding
            resized_image = cv2.resize(image, (0, 0), fx=0.75, fy=0.75)

            # Find face locations
            locations = fr.face_locations(resized_image)
            if not locations:
                print("No faces found in the image")
                return False

            # Get face encodings
            encodings = fr.face_encodings(resized_image, locations)
            if not encodings:
                print("Could not generate face encoding")
                return False

            # Use the first encoding found
            encoding = encodings[0]
            print(f"Generated encoding shape: {encoding.shape}")

            db = get_database()
            collection = db[f"encodings_{company_code}"]
            result = collection.update_one(
                {"employee_code": employee_code},
                {"$set": {
                    "company_code": company_code,
                    "employee_code": employee_code,
                    "branch": branch,
                    "fullname": fullname,
                    "existing_user_officekit": existing_office_kit_user,
                    "encodings": encoding.tolist()
                }},
                upsert=True
            )
            cashe = FaceIndexManager(company_code)
            cashe.add_employee({
                "company_code": company_code,
                "employee_code": employee_code,
                "branch": branch,
                "fullname": fullname,
                "existing_user_officekit": existing_office_kit_user,
                "encodings": encoding.tolist(),
                "_id": result.upserted_id
            })
            return True

        except Exception as e:
            print(f"Error in update_face: {e}")
            return False

    def _log_attendance(self, company_code: str, employee: dict, distance: float):
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        db = get_database()
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
            if last_log["direction"] == "in":
                direction = "out"
                duration = (now - last_log["time"]).total_seconds()
                log_entry["direction"] = "out"

                collection.update_one(
                    filter_query,
                    {
                        "$push": {"log_details": log_entry},
                        "$inc": {"total_working_time": duration}
                    }
                )
            else:
                collection.update_one(
                    filter_query,
                    {"$push": {"log_details": log_entry}}
                )
        else:
            # First check-in of the day
            collection.insert_one({
                "employee_id": employee["employee_code"],
                "fullname": employee["fullname"],
                "company_code": company_code,
                "date": now,
                "total_working_time": 0,
                "present": "P",
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
