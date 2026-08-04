import faiss
import numpy as np
import threading
from typing import Dict, Optional, List
import os
import pickle
from bson import ObjectId
from model.database import get_database

class FaceIndexManager:
    _instances = {}

    def __new__(cls, company_code: str):
        if company_code not in cls._instances:
            instance = super(FaceIndexManager, cls).__new__(cls)
            instance.company_code = company_code
            instance.index: Optional[faiss.IndexHNSWFlat] = None
            instance.vector_to_doc_id: Dict[int, str] = {}
            instance.modify_lock = threading.Lock()
            instance.last_loaded_time = 0
            cls._instances[company_code] = instance
        return cls._instances[company_code]

    def rebuild_index(self):
        """Rebuild FAISS index from DB in batches. Runs under lock to avoid race."""
        with self.modify_lock:
            db = get_database(self.company_code)
            collection = db[f'encodings_{self.company_code}']

            dimension = 128
            # Use HNSW for fast nearest neighbor on millions of records
            new_index = faiss.IndexHNSWFlat(dimension, 32)
            
            vector_to_doc_id = {}
            batch_size = 10000
            
            cursor = collection.find(
                {"is_delete": {"$ne": True}}, 
                {"encodings": 1, "_id": 1}
            ).batch_size(batch_size)
            
            encodings_batch = []
            current_idx = 0
            
            for doc in cursor:
                enc = doc.get("encodings")
                if enc and len(enc) == 128:
                    encodings_batch.append(enc)
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
        """
        Face search — runs without lock.
        FAISS read operations are safe in parallel.
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_dir = os.path.join(base_dir, "faiss_indexes")
        
        # Check if the map file on disk is newer than our memory cache
        map_path = os.path.join(index_dir, f"faiss_map_{self.company_code}.pkl")
        
        if os.path.exists(map_path):
            current_mtime = os.path.getmtime(map_path)
            if current_mtime > self.last_loaded_time:
                self.load_from_disk()
        elif self.index is None:
            self.rebuild_index()

        if self.index is None or self.index.ntotal == 0:
            return []

        query = query_encoding.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query, k * 2)

        results = []
        matched_mongo_ids = []
        valid_matches = []
        
        for dist_l2, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.vector_to_doc_id):
                continue
            distance = np.sqrt(dist_l2)
            if distance > threshold:
                continue
                
            mongo_id = self.vector_to_doc_id.get(idx)
            if mongo_id:
                try:
                    matched_mongo_ids.append(ObjectId(mongo_id))
                    valid_matches.append({
                        "distance": float(distance),
                        "mongo_id": mongo_id
                    })
                except Exception:
                    pass
                
        if not matched_mongo_ids:
            return []
            
        # Fetch metadata from MongoDB on-demand
        db = get_database(self.company_code)
        collection = db[f'encodings_{self.company_code}']
        
        # Retrieve actual documents
        employee_docs = list(collection.find(
            {"_id": {"$in": matched_mongo_ids}},
            {"encodings": 0, "existing_user_officekit": 0, "company_code": 0}
        ))
        
        # Map back to results
        doc_map = {str(doc["_id"]): doc for doc in employee_docs}
        
        for match in valid_matches:
            emp_doc = doc_map.get(match["mongo_id"])
            if emp_doc:
                results.append({
                    "employee": emp_doc,
                    "distance": match["distance"],
                    "mongo_id": match["mongo_id"]
                })

        # Sort the results by distance since MongoDB fetch didn't preserve FAISS distance order
        results.sort(key=lambda x: x["distance"])
        return results

    def add_employee(self, employee_doc: dict):
        if self.index is None:
            self.rebuild_index()
            return

        enc = np.array(employee_doc["encodings"], dtype=np.float32).reshape(1, -1)
        
        with self.modify_lock:
            self.index.add(enc)
            new_id = len(self.vector_to_doc_id)
            self.vector_to_doc_id[new_id] = str(employee_doc["_id"])
            from main import app
            app.logger.info(f"Worker post_fork: initializing FAISS indexes : {new_id}")
            self.save_to_disk()

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
        
        # Save FAISS index natively (fast and memory efficient)
        faiss.write_index(self.index, idx_path)
        
        # Only pickle the lightweight dictionary
        with open(map_path, "wb") as f:
            pickle.dump({"vector_to_doc_id": self.vector_to_doc_id}, f)

    def load_from_disk(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_dir = os.path.join(base_dir, "faiss_indexes")
        
        idx_path = os.path.join(index_dir, f"faiss_index_{self.company_code}.bin")
        map_path = os.path.join(index_dir, f"faiss_map_{self.company_code}.pkl")

        # Fallback for old index format (.pkl instead of .bin)
        old_path = os.path.join(index_dir, f"faiss_index_{self.company_code}.pkl")
        if not os.path.exists(idx_path) and os.path.exists(old_path):
            return self.load_old_format(old_path)

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
        except:
            return False
            
    def load_old_format(self, old_path: str):
        """Migrate from old index structure if it exists."""
        try:
            with open(old_path, "rb") as f:
                data = pickle.load(f)

            with self.modify_lock:
                self.index = faiss.deserialize_index(data["index"])
                self.vector_to_doc_id = data.get("vector_to_doc_id", {})
                self.last_loaded_time = os.path.getmtime(old_path)
            
            # Immediately save to the new format
            self.save_to_disk()
            # Remove the old file
            try:
                os.remove(old_path)
            except Exception:
                pass
            return True
        except Exception:
            return False
