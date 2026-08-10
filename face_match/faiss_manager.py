import faiss
import numpy as np
import threading
import logging
from typing import Dict, Optional, List
import os
import pickle
from bson import ObjectId
from model.database import get_database

logger = logging.getLogger("faiss_manager")


class FaceIndexManager:
    _instances = {}

    def __new__(cls, company_code: str):
        if company_code not in cls._instances:
            instance = super(FaceIndexManager, cls).__new__(cls)
            instance.company_code = company_code
            instance.index: Optional[faiss.Index] = None
            instance.vector_to_doc_id: Dict[int, str] = {}
            instance.modify_lock = threading.RLock()
            instance.last_loaded_time = 0
            cls._instances[company_code] = instance
        return cls._instances[company_code]

    def rebuild_index(self):
        """Rebuild FAISS index from DB in batches. Uses exact IndexFlatL2."""
        with self.modify_lock:
            db = get_database(self.company_code)
            collection = db[f'encodings_{self.company_code}']

            dimension = 128
            new_index = faiss.IndexFlatL2(dimension)

            vector_to_doc_id: Dict[int, str] = {}
            batch_size = 10000

            cursor = collection.find(
                {"is_delete": {"$ne": True}},
                {"encodings": 1, "_id": 1, "employee_code": 1}
            ).batch_size(batch_size)

            encodings_batch = []
            current_idx = 0

            for doc in cursor:
                enc_data = doc.get("encodings")
                if not enc_data:
                    continue

                # Handle multi-pose (list of lists) vs legacy single pose (list of floats)
                poses = enc_data if isinstance(enc_data[0], list) else [enc_data]

                for pose_vec in poses:
                    if isinstance(pose_vec, list) and len(pose_vec) == dimension:
                        encodings_batch.append(pose_vec)
                        vector_to_doc_id[current_idx] = str(doc["_id"])
                        current_idx += 1

                        if len(encodings_batch) >= batch_size:
                            encodings_np = np.array(encodings_batch, dtype=np.float32)
                            new_index.add(encodings_np)
                            encodings_batch = []

            if encodings_batch:
                encodings_np = np.array(encodings_batch, dtype=np.float32)
                new_index.add(encodings_np)

            if current_idx == 0:
                self.index = None
                self.vector_to_doc_id = {}
                return

            self.index = new_index
            self.vector_to_doc_id = vector_to_doc_id
            self.save_to_disk()

    def search(self, query_encoding: np.ndarray, k: int = 5, threshold: float = 0.6):
        """Face search — safe for parallel reads."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_dir = os.path.join(base_dir, "faiss_indexes")

        map_path = os.path.join(index_dir, f"faiss_map_{self.company_code}.pkl")

        if os.path.exists(map_path):
            current_mtime = os.path.getmtime(map_path)
            if self.index is None or current_mtime > self.last_loaded_time:
                self.load_from_disk()
        elif self.index is None:
            self.rebuild_index()

        query = query_encoding.astype(np.float32).reshape(1, -1)

        # Check dimension match — if index on disk has different dimension, force rebuild
        if self.index is None or self.index.d != query.shape[1]:
            logger.info(f"[{self.company_code}] FAISS index dimension mismatch or uninitialized. Rebuilding index...")
            self.rebuild_index()

        if self.index is None or self.index.ntotal == 0:
            return []

        if query.shape[1] != self.index.d:
            logger.error(f"[{self.company_code}] Dimension mismatch even after rebuild (query: {query.shape[1]}, index: {self.index.d})")
            return []

        search_k = min(k * 2, self.index.ntotal)
        distances, indices = self.index.search(query, search_k)

        matched_mongo_ids = []
        valid_matches = []

        for dist_l2, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.vector_to_doc_id):
                continue
            distance = float(np.sqrt(dist_l2))
            if distance > threshold:
                continue

            mongo_id = self.vector_to_doc_id.get(idx)
            if mongo_id:
                try:
                    matched_mongo_ids.append(ObjectId(mongo_id))
                    valid_matches.append({
                        "distance": distance,
                        "mongo_id": mongo_id
                    })
                except Exception:
                    pass

        if not matched_mongo_ids:
            return []

        db = get_database(self.company_code)
        collection = db[f'encodings_{self.company_code}']

        employee_docs = list(collection.find(
            {"_id": {"$in": matched_mongo_ids}},
            {"encodings": 0, "existing_user_officekit": 0, "company_code": 0}
        ))

        doc_map = {str(doc["_id"]): doc for doc in employee_docs}

        # Collapse multi-pose matches to best distance per employee
        best_per_employee = {}
        for match in valid_matches:
            emp_doc = doc_map.get(match["mongo_id"])
            if not emp_doc:
                continue
            key = match["mongo_id"]
            if key not in best_per_employee or match["distance"] < best_per_employee[key]["distance"]:
                best_per_employee[key] = {
                    "employee": emp_doc,
                    "distance": match["distance"],
                    "mongo_id": match["mongo_id"]
                }

        results = list(best_per_employee.values())
        results.sort(key=lambda x: x["distance"])
        return results

    def add_employee(self, employee_doc: dict):
        with self.modify_lock:
            self.rebuild_index()

    def remove_employee(self, mongo_id: str):
        with self.modify_lock:
            self.rebuild_index()

    def save_to_disk(self):
        if self.index is None:
            return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_dir = os.path.join(base_dir, "faiss_indexes")
        os.makedirs(index_dir, exist_ok=True)

        idx_path = os.path.join(index_dir, f"faiss_index_{self.company_code}.bin")
        map_path = os.path.join(index_dir, f"faiss_map_{self.company_code}.pkl")

        faiss.write_index(self.index, idx_path)

        with open(map_path, "wb") as f:
            pickle.dump({"vector_to_doc_id": self.vector_to_doc_id}, f)
        self.last_loaded_time = os.path.getmtime(map_path)

    def load_from_disk(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_dir = os.path.join(base_dir, "faiss_indexes")

        idx_path = os.path.join(index_dir, f"faiss_index_{self.company_code}.bin")
        map_path = os.path.join(index_dir, f"faiss_map_{self.company_code}.pkl")

        if not os.path.exists(idx_path) or not os.path.exists(map_path):
            return False

        try:
            with self.modify_lock:
                self.index = faiss.read_index(idx_path)
                with open(map_path, "rb") as f:
                    data = pickle.load(f)
                    self.vector_to_doc_id = data.get("vector_to_doc_id", {})
                self.last_loaded_time = os.path.getmtime(map_path)
            return True
        except Exception as e:
            logger.error(f"Failed to load FAISS index from disk: {e}")
            return False
