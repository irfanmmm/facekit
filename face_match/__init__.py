from .face_ml import FaceAttendance
from .faiss_manager import FaceIndexManager

def init_faiss_indexes():
    from .faiss_manager import FaceIndexManager
    from model.database import get_database

    db = get_database()
    collections = db.list_collection_names()
    encoding_cols = [c for c in collections if c.startswith("encodings_")]

    for col in encoding_cols:
        company_code = col.replace("encodings_", "")
        print(f"Building FAISS index for company: {company_code}")
        manager = FaceIndexManager(company_code)
        manager.rebuild_index()