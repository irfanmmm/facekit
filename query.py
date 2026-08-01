from dotenv import load_dotenv
load_dotenv()
from model.database import get_database

client = get_database()
dbs = client.list_database_names()
companies = [db for db in dbs if db.startswith('A') and len(db) >= 4 and db[1:].isdigit()]
print(f"Total companies: {len(companies)}")

for comp in companies[:1]:
    print(f"Checking company {comp}")
    db = get_database(comp)
    enc_col = db[f'encodings_{comp}']
    doc = enc_col.find_one()
    if doc:
        print(f"Sample from {comp}.encodings:")
        print({k: v for k, v in doc.items() if k != 'encodings' and k != '_id'})
