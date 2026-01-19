import faiss
import numpy as np
import threading
from typing import Dict, Optional, List
import os
import pickle
from model.database import get_database
from connection.officekit_punching import OfficeKitPunching


class FaceIndexManager:
    _instances = {}

    def __new__(cls, company_code: str):
        if company_code not in cls._instances:
            instance = super(FaceIndexManager, cls).__new__(cls)
            instance.company_code = company_code
            instance.index: Optional[faiss.IndexFlatL2] = None
            instance.employee_map: List[dict] = []
            instance.vector_to_doc_id: Dict[int, str] = {}
            instance.modify_lock = threading.Lock()
            cls._instances[company_code] = instance
        return cls._instances[company_code]

    def rebuild_index(self):
        """Rebuild FAISS index from DB. Runs under lock to avoid race."""
        with self.modify_lock:
            db = get_database('A337')
            collection = db[f'encodings_A337']
            sdb = get_database('SettingsDB')
            settings = sdb[f'settings_A337']
            val = settings.find_one({
                "setting_name": "Office Kit Integration"
            })
            value = val.get("value")

            docs = list(collection.find({}, {
                "encodings": 1,
                "employee_code": 1,
                "fullname": 1,
                "branch": 1,
                "_id": 1
            }))

            if not docs:
                self.index = None
                self.employee_map = []
                self.vector_to_doc_id = {}
                return

            encodings = []
            valid_docs = []
            for doc in docs:
                enc = doc.get("encodings")
                if enc and len(enc) == 128:
                    encodings.append(np.array(enc, dtype=np.float32))
                    valid_docs.append(doc)

                if value:
                    off = OfficeKitPunching()
                    emp_code = doc.get("employee_code")
                    branch = off.retreve_branche_by_user(emp_code)
                    if branch['branchId'] is not None:
                        collection.update_one(
                            {"_id": doc["_id"]},
                            {
                                "$set": {
                                    "branch": branch['branchId'],
                                }
                            }
                        )

            if not encodings:
                self.index = None
                return

            encodings_np = np.vstack(encodings)
            dimension = 128
            new_index = faiss.IndexFlatL2(dimension)
            new_index.add(encodings_np)

            self.index = new_index
            self.employee_map = valid_docs
            self.vector_to_doc_id = {
                i: str(doc["_id"]) for i, doc in enumerate(valid_docs)
            }

    def search(self, query_encoding: np.ndarray, k: int = 5, threshold: float = 0.6):
        """
        Face search — runs without lock.
        FAISS read operations are safe in parallel.
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        query = query_encoding.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query, k * 2)

        results = []
        for dist_l2, idx in zip(distances[0], indices[0]):
            if idx >= len(self.employee_map):
                continue

            distance = np.sqrt(dist_l2)
            if distance > threshold:
                continue

            employee_doc = self.employee_map[idx]
            results.append({
                "employee": employee_doc,
                "distance": float(distance),
                "mongo_id": self.vector_to_doc_id.get(idx)
            })

        return results

    def add_employee(self, employee_doc: dict):

        if self.index is None:
            self.rebuild_index()
            return

        enc = np.array(employee_doc["encodings"],
                       dtype=np.float32).reshape(1, -1)
        self.index.add(enc)

        new_id = len(self.employee_map)
        self.employee_map.append(employee_doc)
        self.vector_to_doc_id[new_id] = str(employee_doc["_id"])
        from main import app
        app.logger.info(
            f"Worker post_fork: initializing FAISS indexes : {new_id}")

    def remove_employee(self, mongo_id: str):
        with self.modify_lock:
            self.rebuild_index()

    def save_to_disk(self, path: str = None):
        if path is None:
            path = f"faiss_index_{self.company_code}.pkl"

        with self.modify_lock:
            if self.index is None:
                return
            data = {
                "index": faiss.serialize_index(self.index),
                "employee_map": self.employee_map,
                "vector_to_doc_id": self.vector_to_doc_id
            }
            with open(path, "wb") as f:
                pickle.dump(data, f)

    def load_from_disk(self, path: str = None):
        if path is None:
            path = f"faiss_index_{self.company_code}.pkl"

        if not os.path.exists(path):
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)

            with self.modify_lock:
                self.index = faiss.deserialize_index(data["index"])
                self.employee_map = data["employee_map"]
                self.vector_to_doc_id = data["vector_to_doc_id"]
            return True
        except:
            return False
