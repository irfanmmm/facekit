import faiss
import numpy as np
import threading
from typing import Dict, Optional, List
from bson import ObjectId
import os
import pickle
from model.database import get_database


class FaceIndexManager:
    _instances = {}
    _locks = {}

    def __new__(cls, company_code: str):
        if company_code not in cls._instances:
            instance = super(FaceIndexManager, cls).__new__(cls)
            instance.company_code = company_code
            instance.index: Optional[faiss.IndexFlatL2] = None
            # Maps FAISS vector ID → employee doc
            instance.employee_map: List[dict] = []
            # FAISS ID → Mongo _id
            instance.vector_to_doc_id: Dict[int, str] = {}
            instance.lock = threading.Lock()
            cls._instances[company_code] = instance
            cls._locks[company_code] = threading.Lock()
        return cls._instances[company_code]

    def rebuild_index(self):
        """Rebuild FAISS index from MongoDB (call this on startup & when employees change)"""
        with self.lock:
            db = get_database(self.company_code)
            collection = db[f'encodings_{self.company_code}']

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

            # Extract encodings
            encodings = []
            valid_docs = []
            for doc in docs:
                enc = doc.get("encodings")
                if enc and len(enc) == 128:
                    encodings.append(np.array(enc, dtype=np.float32))
                    valid_docs.append(doc)

            if not encodings:
                self.index = None
                return

            encodings_np = np.vstack(encodings)

            # Create new index
            dimension = 128
            new_index = faiss.IndexFlatL2(dimension)
            # Optional: use IVF for >50k employees
            # new_index = faiss.IndexIVFFlat(faiss.IndexFlatL2(dimension), dimension, 100)
            # quantizer = faiss.IndexFlatL2(dimension)
            # new_index = faiss.IndexIVFFlat(quantizer, dimension, 100)
            # new_index.train(encodings_np)

            new_index.add(encodings_np)

            # Update in-memory state
            self.index = new_index
            self.employee_map = valid_docs
            self.vector_to_doc_id = {
                i: str(doc["_id"]) for i, doc in enumerate(valid_docs)}


    def search(self, query_encoding: np.ndarray, k: int = 5, threshold: float = 0.6):
        """Return list of (employee_doc, distance)"""
        if self.index is None or self.index.ntotal == 0:
            return []

        query = query_encoding.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(
            query, k * 2)  # search more, filter later

        results = []
        for dist_l2, idx in zip(distances[0], indices[0]):
            if idx >= len(self.employee_map):
                continue
            # Convert L2 → Euclidean (face_recognition uses this)
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
        """Add single employee and update index"""
        # with self.lock:
        if self.index is None:
            self.rebuild_index()
            return

        enc = np.array(employee_doc["encodings"],
                       dtype=np.float32).reshape(1, -1)
        self.index.add(enc)
        new_id = len(self.employee_map)
        self.employee_map.append(employee_doc)
        self.vector_to_doc_id[new_id] = str(employee_doc["_id"])

    def remove_employee(self, mongo_id: str):
        """Remove employee by MongoDB _id (not perfect with FlatL2, rebuild recommended)"""
        # For FlatL2, removal is not efficient → just rebuild
        self.rebuild_index()

    def save_to_disk(self, path: str = None):
        """Optional: persist index to disk"""
        if path is None:
            path = f"faiss_index_{self.company_code}.pkl"
        with self.lock:
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
            self.index = faiss.deserialize_index(data["index"])
            self.employee_map = data["employee_map"]
            self.vector_to_doc_id = data["vector_to_doc_id"]
            return True
        except:
            return False
