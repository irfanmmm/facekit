import os
import csv
import numpy as np
from model.database import _get_client
from face_match.faiss_manager import FaceIndexManager

def main():
    client = _get_client()
    databases = client.list_database_names()
    
    exclude_dbs = ["admin", "config", "local", "SettingsDB", "sample_mflix"]
    
    with open('duplicate_faces.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Company Code", "Employee 1 Name", "Employee 1 Code", "Emp 1 Created Date", "Employee 2 Name", "Employee 2 Code", "Emp 2 Created Date", "Distance"])
        
        for db_name in databases:
            if db_name in exclude_dbs:
                continue
                
            company_code = db_name
            db = client[db_name]
            collection_name = f'encodings_{company_code}'
            
            if collection_name not in db.list_collection_names():
                continue
                
            collection = db[collection_name]
            
            # Fetch all active records with v2 encodings
            records = list(collection.find(
                {"is_delete": {"$ne": True}, "encodings_v2": {"$exists": True}},
                {"fullname": 1, "employee_code": 1, "encodings_v2": 1, "name": 1, "_id": 1}
            ))
            
            if not records:
                continue
                
            print(f"Checking {len(records)} records for company {company_code} using FAISS algorithm...")
            
            # Initialize FAISS manager for the company
            manager = FaceIndexManager(company_code)
            # Ensure the index is loaded or rebuilt
            manager.search(np.zeros(128, dtype=np.float32), k=1) 
            
            seen_pairs = set()

            for rec in records:
                enc_data = rec.get("encodings_v2")
                if not enc_data:
                    continue
                    
                poses = enc_data if isinstance(enc_data[0], list) else [enc_data]
                
                for pose in poses:
                    if not (isinstance(pose, list) and len(pose) == 128):
                        continue
                        
                    pose_arr = np.array(pose, dtype=np.float32)
                    
                    # Search using the exact same algorithm as the API
                    candidates = manager.search(pose_arr, k=10, threshold=0.85)
                    
                    for match in candidates:
                        matched_id = match.get("mongo_id")
                        # Ignore self-match
                        if matched_id == str(rec["_id"]):
                            continue
                            
                        distance = match.get("distance")
                        matched_emp = match.get("employee")
                        
                        # Sort IDs to prevent duplicate pairs (A->B and B->A)
                        pair = tuple(sorted([str(rec["_id"]), matched_id]))
                        if pair in seen_pairs:
                            continue
                            
                        seen_pairs.add(pair)
                        
                        name1 = rec.get("fullname", rec.get("name", "Unknown"))
                        code1 = rec.get("employee_code", "Unknown")
                        date1 = rec["_id"].generation_time.strftime('%Y-%m-%d') if "_id" in rec else "Unknown"
                        
                        name2 = matched_emp.get("fullname", matched_emp.get("name", "Unknown"))
                        code2 = matched_emp.get("employee_code", "Unknown")
                        date2 = matched_emp["_id"].generation_time.strftime('%Y-%m-%d') if "_id" in matched_emp else "Unknown"
                        
                        writer.writerow([company_code, name1, code1, date1, name2, code2, date2, round(distance, 4)])
                        print(f"Found duplicate: {name1} vs {name2} (Dist: {distance:.4f})")

if __name__ == "__main__":
    main()
