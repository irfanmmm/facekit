from datetime import datetime, timedelta, time
import face_recognition as fr
import cv2
import numpy as np
from threading import Lock
from model.database import get_database
from sklearn.neighbors import KDTree
from flask import Flask


app = Flask(__name__)
# import traceback

# Global cache
KNOWN_ENCODINGS = {}
WORKING_HOURS = 8
CUTOFF_TIME = time(23, 59) # example cutoff
lock = Lock()


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

    def update_face(self, employee_code, add_img, company_code, fullname):
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
            collection.update_one(
                {"employee_code": employee_code},
                {"$set": {
                    "company_code": company_code,
                    "employee_code": employee_code,
                    "fullname": fullname,
                    "encodings": encoding.tolist()  # Store as list for MongoDB
                }},
                upsert=True
            )
            return True
            
        except Exception as e:
            print(f"Error in update_face: {e}")
            return False
    
    def crop_with_landmarks(self,image, landmarks, target_size=(256, 256)):
        h_img, w_img = image.shape[:2]

        x = int(float(landmarks["x"]) * w_img)
        y = int(float(landmarks["y"]) * h_img)
        w = int(float(landmarks["width"]) * w_img)
        h = int(float(landmarks["height"]) * h_img)

        # Safe crop
        x = max(0, min(x, w_img - 1))
        y = max(0, min(y, h_img - 1))
        w = min(w, w_img - x)
        h = min(h, h_img - y)

        face_crop = image[y:y+h, x:x+w]
        if face_crop.size == 0:
            return None

        return cv2.resize(face_crop, target_size)


    def compare_faces(self, base_img, company_code, model="hog"):
        try:
            file_bytes = np.frombuffer(base_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if image is None:
                print("Could not decode image")
                return False

            # Resize image - not too aggressive
            resized_img = cv2.resize(image, (0, 0),fx=0.5, fy=0.5)
            print(f"Image shape after resize: {resized_img.shape}")

            # Find faces
            face_locations = fr.face_locations(resized_img, model=model)
            print(f"Found {len(face_locations)} faces")
            
            if not face_locations:
                return False

            # Get current face encoding
            current_encodings = fr.face_encodings(resized_img, face_locations, num_jitters=1)
            if not current_encodings:
                return False
            
            current_encoding = current_encodings[0]
            print(f"Current encoding shape: {current_encoding.shape}")
            print(f"Current encoding sample: {current_encoding[:5]}")  # First 5 values
            
            # Get database
            db = get_database()
            collection = db[f'encodings_{company_code}']
            
            # Get all stored employees
            stored_employees = list(collection.find())
            print(f"Found {len(stored_employees)} stored employees")
            
            # Debug each comparison individually
            matches_found = []
            distances = []
            
            for i, employee in enumerate(stored_employees):
                try:
                    # Get stored encoding
                    stored_encoding = np.array(employee['encodings'], dtype=np.float64)
                    print(f"\nEmployee {i}: {employee['fullname']}")
                    print(f"Stored encoding shape: {stored_encoding.shape}")
                    print(f"Stored encoding sample: {stored_encoding[:5]}")
                    
                    # Calculate distance (lower = more similar)
                    distance = fr.face_distance([stored_encoding], current_encoding)[0]
                    distances.append(distance)
                    print(f"Face distance: {distance}")
                    
                    # Test with different tolerance levels
                    tolerances = [0.4, 0.5, 0.6, 0.7]
                    for tolerance in tolerances:
                        match = fr.compare_faces([stored_encoding], current_encoding, tolerance=tolerance)[0]
                        print(f"  Tolerance {tolerance}: {'MATCH' if match else 'NO MATCH'}")
                    
                    # Use strict tolerance for actual matching
                    is_match = fr.compare_faces([stored_encoding], current_encoding, tolerance=0.5)[0]
                    if is_match:
                        matches_found.append({
                            'employee': employee,
                            'distance': distance,
                            'index': i
                        })
                        
                except Exception as e:
                    print(f"Error processing employee {employee.get('fullname', 'Unknown')}: {e}")
                    continue
            
            print(f"\nSUMMARY:")
            print(f"Total comparisons: {len(stored_employees)}")
            print(f"Matches found: {len(matches_found)}")
            print(f"Average distance: {np.mean(distances):.4f}")
            print(f"Min distance: {np.min(distances):.4f}")
            print(f"Max distance: {np.max(distances):.4f}")
            
            # If multiple matches, choose the one with smallest distance (most similar)
            if matches_found:
                best_match = min(matches_found, key=lambda x: x['distance'])
                print(f"Best match: {best_match['employee']['fullname']} (distance: {best_match['distance']:.4f})")
                
                # Log attendance for best match only
                matched_employee = best_match['employee']
                attandance_collectiion = db[f"attandance_{company_code}_{datetime.utcnow().strftime('%Y-%m')}"]
                total_duration = timedelta()
                # # 3. Convert to H:M:S
                total_seconds = int(total_duration.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                formatted = f"{hours:02}:{minutes:02}:{seconds:02}"
                
                now = datetime.now()
                today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today + timedelta(days=1)

                _filter = {"employee_id":matched_employee['employee_code'],"date": {"$gte": today, "$lt": tomorrow}}
                todays_record = attandance_collectiion.find_one(_filter)
                direction = "in"

                if not todays_record:
                    attandance_record = {
                        "employee_id":matched_employee['employee_code'],
                        "fullname": matched_employee["fullname"],
                        "company_code": company_code,
                        "date":now,
                        "total_working_time":0,
                        "present":"P",
                        "log_details":[{"direction":direction,"time":now,"confidence_distance": float(best_match['distance']), }]
                    }
                    attandance_collectiion.insert_one(attandance_record)
                else:
                    log_details = todays_record['log_details']
                    # i = len(log_details) -1
                    last_record = log_details[-1]
                    if last_record['direction'] == 'in':
                        # last_time = datetime.strptime(last_record['time'], "%Y-%m-%d %H:%M:%S")
                        duration_seconds = (now - last_record['time']).total_seconds()
                        # hours = int(duration_seconds // 3600)
                        # minutes = int((duration_seconds % 3600) // 60)
                        # seconds = int(duration_seconds % 60)
                        direction = "Out"
                        attandance_collectiion.update_one(
                            _filter,
                            {
                                "$push": {"log_details": {"direction": "out", "time": now}},
                                "$inc": {"total_working_time": duration_seconds},
                                "$set": {"confidence_distance": float(best_match['distance'])}
                            }
                        )
                    else:
                        direction = "in"
                        attandance_collectiion.update_one(
                            _filter,
                            {
                                "$push": {"log_details": {"direction": "in", "time": now}},
                                "$set": {"confidence_distance": float(best_match['distance'])}
                            },
                            
                        )
                
                return {
                    "fullname": matched_employee['fullname'],
                    "employee_code": matched_employee['employee_code'],
                    "direction": direction,
                    "confidence_distance": best_match['distance']
                }
            else:
                print("No matches found with current tolerance")
                return False
                
        except Exception as e:
            print(f"Error in compare_faces: {e}")
            import traceback
            print(traceback.format_exc())
            return False

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

        

db = get_database()
def job():
    for colloction_name in db.list_collection_names():
        print("called...",colloction_name)
        compony_code = colloction_name.endswith(f"{datetime.utcnow().strftime('%Y-%m')}")
        if not compony_code:
            continue
        
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        _filter = {"date": {"$gte": today, "$lt": tomorrow}}

        if now.time() <= CUTOFF_TIME:
            continue

        for log in db[colloction_name].find(_filter):
            duration_seconds = log['total_working_time']
            hours = int(duration_seconds // 3600)
            if hours < WORKING_HOURS:
                required_seconds = WORKING_HOURS * 3600  
                shortage_seconds = max(0, required_seconds - duration_seconds)
                sh_hours = int(shortage_seconds // 3600)
                sh_minutes = int((shortage_seconds % 3600) // 60)
                sh_seconds = int(shortage_seconds % 60)
                db[colloction_name].update_one(
                    {"_id": log["_id"]},
                    {
                        "$set": {
                                "present": "L",
                                "shortage":f"{sh_hours:2}:{sh_minutes:2}:{sh_seconds:2}"
                            }
                    }
                )