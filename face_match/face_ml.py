from datetime import datetime, timedelta
import face_recognition as fr
import cv2
import numpy as np
from threading import Lock
from model.database import get_database
from sklearn.neighbors import KDTree

# Global cache
# KNOWN_IMAGES = []
KNOWN_ENCODINGS = {}
lock = Lock()
today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
today_end = today_start + timedelta(days=1)
class FaceAttendance:
    def __init__(self):
        # Load cache from DB on init
        self.trees = {}
        self.emp_maps = {}  # map index -> employee_id
        self.load_all_faces()

    def build_tree(self, company_code):
        """Build KDTree for a company"""
        employees = KNOWN_ENCODINGS.get(company_code, {})
        if not employees:
            return

        encodings = []
        emp_ids = []
        for emp_id, emp in employees.items():
            encodings.append(np.array(emp["encodings"], dtype=np.float32))
            emp_ids.append(emp_id)

        if encodings:
            self.trees[company_code] = KDTree(encodings)
            self.emp_maps[company_code] = emp_ids

    def update_face(self, employee_code, add_img, compony_code, fullname):
        try:
            # Load full-resolution image for accurate encoding
            image = fr.load_image_file(add_img)
            # small_img = cv2.resize(image, (0, 0), fx=0.25, fy=0.25)

            face_locations = fr.face_locations(image, model="hog")
            if not face_locations:
                return False
            encoding = fr.face_encodings(image, face_locations)[0]

            # # check if same user face exists
            # for emp in KNOWN_ENCODINGS.get(compony_code, {}).values():
            #     print(emp)

            # matches = fr.compare_faces([np.array(emp["encodings"], dtype=np.float32) for emp in KNOWN_ENCODINGS.get(compony_code, {}).values()], encoding, tolerance=0.4)
            # if matches and True in matches:
            #     return False




            encoding_list = encoding.tolist()


            # Save in DB
            db = get_database()
            collection = db[f"encodings_{compony_code}"]
            collection.update_one(
                {"employee_code": employee_code},
                {"$set": {
                    "company_code": compony_code,
                    "employee_code": employee_code,
                    "fullname": fullname,
                    "encoding": encoding_list
                }},
                upsert=True
            )
            # Update in-memory cache
            with lock:
                if compony_code not in KNOWN_ENCODINGS:
                    KNOWN_ENCODINGS[compony_code] = {}

                KNOWN_ENCODINGS[compony_code][employee_code] = {
                    "fullname": fullname,
                    "encodings": encoding_list
                }

            return True
        except Exception as e:
            print(f"Error updating face: {e}")
            return False


    def compare_faces(self, base_img, company_code, tolerance=0.45):
        try:
            # ✅ Resize for speed
            image = fr.load_image_file(base_img)
            small_img = cv2.resize(image, (0, 0), fx=0.2, fy=0.2)

            face_locations = fr.face_locations(small_img, model="hog")
            if not face_locations:
                return False

            test_encoding = fr.face_encodings(small_img, face_locations)[0]
        except Exception as e:
            print(f"Encoding error: {e}")
            return False

        # ✅ Make sure KDTree exists
        if company_code not in self.trees:
            self.build_tree(company_code)

        if company_code not in self.trees:
            return False

        # ✅ Query nearest neighbor
        dist, ind = self.trees[company_code].query([test_encoding], k=1)
        best_distance = dist[0][0]
        best_emp_id = self.emp_maps[company_code][ind[0][0]]

        if best_distance <= tolerance:
            emp = KNOWN_ENCODINGS[company_code][best_emp_id]
            db = get_database()
            collection = db[f"log_{company_code}_{datetime.utcnow().strftime('%Y-%m')}"]
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            emp_last_record = collection.find_one(
                {"employee_id": best_emp_id, "timestamp": {"$gte": today_start, "$lt": today_end}},
                sort=[("timestamp", -1)]  # latest first
            )

            # Determine direction
            if emp_last_record is None:
                direction = "in"   # first punch of the day
            elif emp_last_record["direction"] == "in":
                direction = "out"  # alternate
            else:
                direction = "in"   # next punch after out

            # Insert new attendance record
            record = {
                "employee_id": best_emp_id,
                "fullname": emp["fullname"],
                "company_code": company_code,
                "distance": float(best_distance),
                "direction": direction,
                "timestamp": datetime.utcnow()
            }
            collection.insert_one(record)

            data = {
                "employee_id": best_emp_id,
                "fullname": emp["fullname"],
                "company_code": company_code,
                "distance": float(best_distance),
                "direction": direction,
                "timestamp": str(np.datetime64('now'))
            }

            return data

    def load_all_faces(self):
        """Load all encodings from DB into memory cache."""
        try:
            db = get_database()
            collection_list = db.list_collection_names()
            print("Collections:", collection_list)
            with lock:
                KNOWN_ENCODINGS.clear()
                for collection in collection_list:
                    if not collection.startswith("encodings_"):
                        continue

                    compony_code = collection.split("encodings_")[1]
                    KNOWN_ENCODINGS[compony_code] = {}

                    for emp in db[collection].find():
                        KNOWN_ENCODINGS[compony_code][emp["employee_code"]] = {
                            "fullname": emp["fullname"],
                            "encodings": emp["encoding"]
                        }
                print("Cache loaded:", KNOWN_ENCODINGS.keys())
            return True
        except Exception as e:
            print(f"DB Load Error: {e}")
            return False

# shaduler for marking attandance
# def add_attendance_record(company_code, best_emp_id, best_distance, tolerance=0.6):
#     if best_distance > tolerance:
#         return False
    
#     emp = KNOWN_ENCODINGS[company_code][best_emp_id]
    
#     data = {
#         "employee_id": best_emp_id,
#         "fullname": emp["fullname"],
#         "distance": float(best_distance),
#         "direction": "in" if best_distance < 0.4 else "out",
#         "timestamp": datetime.utcnow()
#     }
    
#     month_str = datetime.utcnow().strftime("%Y-%m")
    
#     # collection.update_one(
#     #     {"company_code": company_code, "month": month_str},
#     #     {"$push": {"records": data}},
#     #     upsert=True
#     # )
    
#     # print(f"Attendance added: {data}")
#     return data

# # Example function to check faces and add attendance
# def check_faces_and_add_attendance():
#     print("Checked faces and updated attendance.")
#     db = get_database()
#     month_str = datetime.utcnow().strftime("%Y-%m")
#     print(KNOWN_ENCODINGS)
#     print(month_str)
#     for company_code in KNOWN_ENCODINGS.keys():
#         collection_name = f"log_{company_code}_{month_str}"
#         attendance_log_collection = db[collection_name]
#         print(f"Using collection: {attendance_log_collection}")
#         # Example: attendance_log_collection.update_one(...)
#     # attendance_log_collection = db[f"attendance_log_{month_str}_{}"]


#     return

# # Scheduler setup
# scheduler = BackgroundScheduler()
# scheduler.add_job(check_faces_and_add_attendance, 'interval', seconds=10)  # every 1 sec
# scheduler.start()
