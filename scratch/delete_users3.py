import sys
import os
sys.path.append('/home/ubuntu/facekit/facekit')

from model.database import _get_client
from connection.officekit_punching import OfficeKitPunching
import re

client = _get_client()
db_names = client.list_database_names()
exclude = ["SettingsDB", "admin", "sample_mflix", "local", "config"]

for db_name in db_names:
    if db_name in exclude:
        continue
    db = client[db_name]
    
    # Check all collections that start with encodings_
    for col_name in db.list_collection_names():
        if col_name.startswith('encodings_'):
            company_code = db_name
            collection = db[col_name]
            
            users = list(collection.find({"fullname": {"$regex": "(irfan|thansih|thanish|tansih)", "$options": "i"}}))
            for user in users:
                emp_code = user.get('employee_code')
                print(f"Found {user['fullname']} ({emp_code}) in DB {db_name}")
                
                # Delete from MongoDB
                collection.delete_one({"_id": user["_id"]})
                print(f"Deleted from MongoDB: {emp_code}")
                
                # Delete from OfficeKit
                try:
                    ok_db = OfficeKitPunching(company_code)
                    if ok_db.conn:
                        cursor = ok_db.conn.cursor()
                        cursor.execute("DELETE FROM ATTENDANCELOG_STAGING WHERE UserId = %s", (emp_code,))
                        cursor.execute("DELETE FROM HR_EMP_MASTER WHERE Emp_Code = %s", (emp_code,))
                        ok_db.conn.commit()
                        print(f"Deleted from OfficeKit SQL: {emp_code}")
                except Exception as e:
                    print(f"OfficeKit deletion error: {e}")

