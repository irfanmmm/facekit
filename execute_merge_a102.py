import csv
from datetime import datetime
from model.database import _get_client
from face_match.faiss_manager import FaceIndexManager
import logging

logger = logging.getLogger("merge_duplicates_a102")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
logger.addHandler(ch)

def run_merge():
    client = _get_client()
    company_code = "A102"
    
    db = client[company_code]
    enc_collection = db[f'encodings_{company_code}']
    
    # Get attendance collections
    attendance_colls = [c for c in db.list_collection_names() if c.startswith(f'attandance_{company_code}')]
    
    with open('duplicate_faces.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Company Code"] != company_code:
                continue
                
            code1 = row["Employee 1 Code"]
            date1 = row["Emp 1 Created Date"]
            code2 = row["Employee 2 Code"]
            date2 = row["Emp 2 Created Date"]
            
            if code1 == code2:
                continue
                
            # Determine which is older
            d1 = datetime.strptime(date1, "%Y-%m-%d") if date1 != "Unknown" else datetime.now()
            d2 = datetime.strptime(date2, "%Y-%m-%d") if date2 != "Unknown" else datetime.now()
            
            if d1 <= d2:
                primary_code = code1
                duplicate_code = code2
            else:
                primary_code = code2
                duplicate_code = code1
                
            logger.info(f"Merging {duplicate_code} into {primary_code}...")
            
            primary_doc = enc_collection.find_one({"employee_code": primary_code, "is_delete": {"$ne": True}})
            duplicate_doc = enc_collection.find_one({"employee_code": duplicate_code, "is_delete": {"$ne": True}})
            
            if not primary_doc or not duplicate_doc:
                logger.warning(f"Skipping {primary_code} and {duplicate_code} - one or both are already deleted or missing.")
                continue
                
            # Copy new face (encodings and image) to the primary record
            update_data = {}
            if "encodings" in duplicate_doc:
                update_data["encodings"] = duplicate_doc["encodings"]
            if "encodings_v2" in duplicate_doc:
                update_data["encodings_v2"] = duplicate_doc["encodings_v2"]
            if "image" in duplicate_doc:
                update_data["image"] = duplicate_doc["image"]
                
            if update_data:
                enc_collection.update_one({"_id": primary_doc["_id"]}, {"$set": update_data})
                
            # Mark duplicate as deleted
            enc_collection.update_one({"_id": duplicate_doc["_id"]}, {"$set": {"is_delete": True}})
            
            # Merge MongoDB Attendance
            for att_coll_name in attendance_colls:
                att_coll = db[att_coll_name]
                att_coll.update_many({"employee_id": duplicate_code}, {"$set": {"employee_id": primary_code}})
                
            logger.info(f"Successfully merged {duplicate_code} into {primary_code} in MongoDB.")
            
    # Rebuild FAISS index
    logger.info("Rebuilding FAISS index for A102...")
    FaceIndexManager(company_code).rebuild_index()
    logger.info("Merge complete!")

if __name__ == "__main__":
    run_merge()
