import sys
sys.path.append('/home/ubuntu/facekit/facekit')
from model.database import _get_client
from connection.officekit_punching import OfficeKitPunching

client = _get_client()
for db_name in client.list_database_names():
    if db_name in ["admin", "local", "config"]: continue
    db = client[db_name]
    for col_name in db.list_collection_names():
        users = list(db[col_name].find({"fullname": {"$regex": "(irfan|thansih|thanish|tansih|than)", "$options": "i"}}))
        for u in users:
            emp_code = u.get('employee_code', '')
            print(f"Found {u.get('fullname')} ({emp_code}) in {db_name}.{col_name}")
            db[col_name].delete_one({"_id": u["_id"]})
            print(f"Deleted from MongoDB: {emp_code}")
            
            try:
                ok_db = OfficeKitPunching(db_name)
                if ok_db.conn:
                    cursor = ok_db.conn.cursor()
                    cursor.execute("DELETE FROM ATTENDANCELOG_STAGING WHERE UserId = %s", (emp_code,))
                    cursor.execute("DELETE FROM HR_EMP_MASTER WHERE Emp_Code = %s", (emp_code,))
                    ok_db.conn.commit()
                    print(f"Deleted from OfficeKit SQL: {emp_code}")
            except Exception as e:
                pass
