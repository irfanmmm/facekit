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

    def update_face(self, employee_code, add_img, compony_code, fullname):
        try:
            # Load full-resolution image for accurate encoding
            image = fr.load_image_file(add_img)
            # small_img = cv2.resize(image, (0, 0), fx=0.25, fy=0.25)

            face_locations = fr.face_locations(image, model="hog")
            if not face_locations:
                print("No face detected")
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


    def compare_faces(self, base_img, company_code, tolerance=0.45, resize_factor=0.25, model="hog"):
        """
        Compare a face with known encodings and log attendance.
        Returns a dict with success=True and data on match, or success=False and reason.
        """
        try:
            # --------- 1) Load image (support FileStorage, bytes, ndarray, path) ----------
            image = None

            if hasattr(base_img, "read"):  # Flask FileStorage or file-like
                file_bytes = np.frombuffer(base_img.read(), np.uint8)
                base_img.seek(0)
                bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                if bgr is None:
                    return {"success": False, "reason": "imdecode_failed"}
                image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            elif isinstance(base_img, (bytes, bytearray)):
                file_bytes = np.frombuffer(base_img, np.uint8)
                bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                if bgr is None:
                    return {"success": False, "reason": "imdecode_failed"}
                image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            elif isinstance(base_img, np.ndarray):
                # Assume it's already an image. face_recognition expects RGB.
                image = base_img
                # If it looks like BGR (common from cv2), optionally convert.
                # We won't auto-convert to avoid wrong conversions; user can pass RGB.
                if image.ndim == 3 and image.shape[2] == 3:
                    # Heuristic: if the mean of blue channel is much larger than red,
                    # it might be BGR — convert to RGB.
                    if np.mean(image[:, :, 0]) - np.mean(image[:, :, 2]) > 25:
                        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            else:
                # Let face_recognition handle paths or file-like objects if given
                try:
                    image = fr.load_image_file(base_img)  # returns RGB numpy array
                except Exception as e:
                    return False
            if image is None:
                return False
            # --------- 2) Resize for speed (preserve aspect) ----------
            h, w = image.shape[:2]
            if resize_factor and 0 < resize_factor < 1.0:
                new_w = max(1, int(w * resize_factor))
                new_h = max(1, int(h * resize_factor))
                small_img = cv2.resize(image, (new_w, new_h))
            else:
                small_img = image

            # --------- 3) Face detection + encoding ----------
            face_locations = fr.face_locations(small_img, model=model)
            if not face_locations:
                return False

            encodings = fr.face_encodings(small_img, face_locations, num_jitters=1)
            if not encodings:
                return False

            test_encoding = np.asarray(encodings[0], dtype=np.float32).reshape(1, -1)

        except Exception as e:
            print("Encoding Exception:", e)
            # print(traceback.format_exc())
            return False
        # --------- 4) Ensure KDTree exists and is compatible ----------
        if company_code not in self.trees or self.trees.get(company_code) is None:
            try:
                self.build_tree(company_code)
            except Exception as e:
                print("build_tree error:", e)
                # print(traceback.format_exc())

        if company_code not in self.trees or self.trees.get(company_code) is None:
            return False

        tree = self.trees[company_code]
        emp_map = self.emp_maps.get(company_code, [])

        try:
            # Validate dimensionality
            if hasattr(tree, 'data'):
                tree_dim = tree.data.shape[1]
                if test_encoding.shape[1] != tree_dim:
                    return False
        except Exception:
            # some KDTree wrappers may not expose .data; skip if so
            pass

        # --------- 5) Query nearest neighbor ----------
        try:
            dist, ind = tree.query(test_encoding, k=1)
            best_distance = float(dist[0][0])
            idx = int(ind[0][0])
        except Exception as e:
            print("KDTree query error:", e)
            # print(traceback.format_exc())
            return False

        # Check emp_map bounds
        if idx < 0 or idx >= len(emp_map):
            return False

        best_emp_id = emp_map[idx]

        # --------- 6) Match decision and attendance logging ----------
        if best_distance <= tolerance:
            emp = KNOWN_ENCODINGS.get(company_code, {}).get(best_emp_id)
            if emp is None:
                return False

            db = get_database()
            collection_name = f"log_{company_code}_{datetime.utcnow().strftime('%Y-%m')}"
            collection = db[collection_name]

            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            emp_last_record = collection.find_one(
                {"employee_id": best_emp_id, "timestamp": {"$gte": today_start, "$lt": today_end}},
                sort=[("timestamp", -1)]
            )

            if emp_last_record is None:
                direction = "in"
            elif emp_last_record.get("direction") == "in":
                direction = "out"
            else:
                direction = "in"

            record = {
                "employee_id": best_emp_id,
                "fullname": emp.get("fullname"),
                "company_code": company_code,
                "distance": best_distance,
                "direction": direction,
                "timestamp": datetime.utcnow()
            }
            collection.insert_one(record)

            data = {
                "employee_id": best_emp_id,
                "fullname": emp.get("fullname"),
                "company_code": company_code,
                "distance": best_distance,
                "direction": direction,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            return data

        # No good match
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
