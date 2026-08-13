from pymongo import MongoClient
import re

client = MongoClient('mongodb://localhost:27017/')
db_names = client.list_database_names()

for db_name in db_names:
    if not db_name.startswith('facekit_'):
        continue
    company_code = db_name.split('_')[1]
    db = client[db_name]
    collection = db[f'encodings_{company_code}']
    
    users = collection.find({"fullname": {"$regex": "(irfan|thansih)", "$options": "i"}})
    for user in users:
        print(f"Found {user['fullname']} ({user.get('employee_code')}) in {db_name}")
