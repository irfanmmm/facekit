from datetime import datetime, timedelta
import face_recognition as fr
import cv2
import numpy as np
from threading import Lock
from model.database import get_database
from sklearn.neighbors import KDTree
# import traceback

# Global cache
KNOWN_ENCODINGS = {}
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
            # output_dir = 'admin_images'
            # filename = 'resized_images.jpg'
            # os.makedirs(output_dir, exist_ok=True)
            
            file_bytes = np.frombuffer(add_img.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if image is None:
                return False
                
            # More reasonable resize - keep more detail for better encoding
            resized_image = cv2.resize(image, (0, 0), fx=0.5, fy=0.5)
            # output_path = os.path.join(output_dir, filename)
            # cv2.imwrite(output_path, resized_image)
            
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






            # file_bytes = np.frombuffer(add_img.read(), np.uint8)
            # image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            # if image is None:
            #     raise ValueError("Could not decode image")

            # # Resize
            # small_img = cv2.resize(image, (0, 0), fx=0.05, fy=0.05)

            # os.makedirs(output_dir, exist_ok=True)

            # output_path = os.path.join(output_dir, filename)
            # cv2.imwrite(output_path, small_img)
            # image = None
            # if hasattr(add_img, "read"):  # Flask FileStorage or file-like
            #     file_bytes = np.frombuffer(add_img.read(), np.uint8)
            #     add_img.seek(0)
            #     bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            #     if bgr is None:
            #         return {"success": False, "reason": "imdecode_failed"}
            #     image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            # elif isinstance(add_img, (bytes, bytearray)):
            #     file_bytes = np.frombuffer(add_img, np.uint8)
            #     bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            #     if bgr is None:
            #         return {"success": False, "reason": "imdecode_failed"}
            #     image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            # elif isinstance(add_img, np.ndarray):
            #     # Assume it's already an image. face_recognition expects RGB.
            #     image = add_img
            #     # If it looks like BGR (common from cv2), optionally convert.
            #     # We won't auto-convert to avoid wrong conversions; user can pass RGB.
            #     if image.ndim == 3 and image.shape[2] == 3:
            #         # Heuristic: if the mean of blue channel is much larger than red,
            #         # it might be BGR — convert to RGB.
            #         if np.mean(image[:, :, 0]) - np.mean(image[:, :, 2]) > 25:
            #             image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # else:
            #     # Let face_recognition handle paths or file-like objects if given
            #     try:
            #         image = fr.load_image_file(add_img)  # returns RGB numpy array
            #     except Exception as e:
            #         return False
            # if image is None:
            #     return False
            # # --------- 2) Resize for speed (preserve aspect) ----------
            # h, w = image.shape[:2]
            # if resize_factor and 0 < resize_factor < 1.0:
            #     new_w = max(1, int(w * resize_factor))
            #     new_h = max(1, int(h * resize_factor))
            #     small_img = cv2.resize(image, (new_w, new_h))
            # else:
            #     small_img = image

            # output_dir = "resized_images"
            # os.makedirs(output_dir, exist_ok=True)  # create folder if not exists
            # output_path = os.path.join(output_dir, "resized_face2.jpg")

            #     # Save the resized image
            # cv2.imwrite(output_path, image)

            # # Detect face(s)
            # face_locations = fr.face_locations(small_img, model="hog")
            # if len(face_locations) != 1:
            #     print("No face or multiple faces detected")
            #     return False

            # # ✅ Extract encoding and convert to list of floats
            # encoding = fr.face_encodings(small_img, face_locations, num_jitters=2)[0]
            # encoding_list = [float(x) for x in encoding]

            # ✅ Save to DB (always safe for JSON)
            # db = get_database()
            # collection = db[f"encodings_{company_code}"]
            # collection.update_one(
            #     {"employee_code": employee_code},
            #     {"$set": {
            #         "company_code": company_code,
            #         "employee_code": employee_code,
            #         "fullname": fullname,
            #         "encodings": encoding_list
            #     }},
            #     upsert=True
            # )

            # # ✅ Update in-memory cache
            # with lock:
            #     if company_code not in KNOWN_ENCODINGS:
            #         KNOWN_ENCODINGS[company_code] = {}
            #     KNOWN_ENCODINGS[company_code][employee_code] = {
            #         "fullname": fullname,
            #         "encodings": encoding_list
            #     }

            # # ✅ Rebuild KDTree
            # self.build_tree(company_code)
        
    
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
            resized_img = cv2.resize(image, (0, 0), fx=0.5, fy=0.5)
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
                log_collection = db[f"log_{company_code}_{datetime.utcnow().strftime('%Y-%m')}"]
                
                # Determine direction
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                
                emp_last_record = log_collection.find_one(
                    {"employee_id": matched_employee['employee_code'], 
                    "timestamp": {"$gte": today_start, "$lt": today_end}},
                    sort=[("timestamp", -1)]
                )
                
                direction = "in"
                if emp_last_record and emp_last_record.get("direction") == "in":
                    direction = "out"
                
                # Log the attendance
                record = {
                    "employee_id": matched_employee['employee_code'],
                    "fullname": matched_employee["fullname"],
                    "company_code": company_code,
                    "direction": direction,
                    "timestamp": datetime.utcnow(),
                    "confidence_distance": float(best_match['distance'])  # Store confidence
                }
                log_collection.insert_one(record)
                
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
        # # --------- 4) Ensure KDTree exists and is compatible ----------
        # if company_code not in self.trees or self.trees.get(company_code) is None:
        #     try:
        #         self.build_tree(company_code)
        #     except Exception as e:
        #         print("build_tree error:", e)
        #         # print(traceback.format_exc())

        # if company_code not in self.trees or self.trees.get(company_code) is None:
        #     return False

        # tree = self.trees[company_code]
        # emp_map = self.emp_maps.get(company_code, [])

        # try:
        #     # Validate dimensionality
        #     if hasattr(tree, 'data'):
        #         tree_dim = tree.data.shape[1]
        #         if test_encoding.shape[1] != tree_dim:
        #             return False
        # except Exception:
        #     # some KDTree wrappers may not expose .data; skip if so
        #     pass

        # # --------- 5) Query nearest neighbor ----------
        # try:
        #     dist, ind = tree.query(test_encoding, k=1)
        #     best_distance = float(dist[0][0])
        #     idx = int(ind[0][0])
        # except Exception as e:
        #     print("KDTree query error:", e)
        #     # print(traceback.format_exc())
        #     return False

        # # Check emp_map bounds
        # if idx < 0 or idx >= len(emp_map):
        #     return False

        # best_emp_id = emp_map[idx]

        # # --------- 6) Match decision and attendance logging ----------
        # if best_distance <= tolerance:
        #     emp = KNOWN_ENCODINGS.get(company_code, {}).get(best_emp_id)
        #     if emp is None:
        #         return False

        #     db = get_database()
        #     collection_name = f"log_{company_code}_{datetime.utcnow().strftime('%Y-%m')}"
        #     collection = db[collection_name]

        #     today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        #     today_end = today_start + timedelta(days=1)

        #     emp_last_record = collection.find_one(
        #         {"employee_id": best_emp_id, "timestamp": {"$gte": today_start, "$lt": today_end}},
        #         sort=[("timestamp", -1)]
        #     )

        #     if emp_last_record is None:
        #         direction = "in"
        #     elif emp_last_record.get("direction") == "in":
        #         direction = "out"
        #     else:
        #         direction = "in"

        #     record = {
        #         "employee_id": best_emp_id,
        #         "fullname": emp.get("fullname"),
        #         "company_code": company_code,
        #         "distance": best_distance,
        #         "direction": direction,
        #         "timestamp": datetime.utcnow()
        #     }
        #     collection.insert_one(record)

        #     data = {
        #         "employee_id": best_emp_id,
        #         "fullname": emp.get("fullname"),
        #         "company_code": company_code,
        #         "distance": best_distance,
        #         "direction": direction,
        #         "timestamp": datetime.utcnow().isoformat() + "Z"
        #     }
        #     return data

        # # No good match
        # return False

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
