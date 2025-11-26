from .face_ml import FaceAttendance
from .faiss_manager import FaceIndexManager
from model.database import exclude
# databases to skip
import re


def init_faiss_indexes():
    from model.database import get_database
    db_client = get_database()  # returns MongoClient
    database_names = db_client.list_database_names()

    for dbname in database_names:
        if dbname in exclude:
            continue
        if not re.match(r"^(A?\d+)$", dbname):
            print(f"Skipping invalid db name: {dbname}")
            continue

        print(f"\nChecking database: {dbname}")
        db = db_client[dbname]

        # Get all collections in this database
        collections = db.list_collection_names()

        # Find collections like encodings_140, encodings_250 etc
        encoding_cols = [col for col in collections if col.startswith("encodings_")]

        if not encoding_cols:
            print(f"No encoding collections found in DB: {dbname}")
            continue

        # Build FAISS index for each collection
        for col in encoding_cols:
            company_code = col.replace("encodings_", "")

            print(f" → Building FAISS index for company_code: {company_code}")

            try:
                manager = FaceIndexManager(company_code)
                manager.rebuild_index()
                print(f" ✓ Completed FAISS index for {company_code}")
            except Exception as e:
                print(f" ❌ Failed to build index for {company_code}: {e}")
