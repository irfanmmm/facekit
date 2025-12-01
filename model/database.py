from pymongo import MongoClient
import os

# CONNECTION_URL = "mongodb://localhost:27017/"
exclude = ["SettingsDB", "admin", "sample_mflix", "local"]
def get_database(db_name=None):
    CONNECTION_URL = os.getenv("DATABASE_URL")
    client = MongoClient(CONNECTION_URL)

    # If db_name is not provided, return client itself
    if not db_name:
        return client

    # Check if DB exists
    existing_dbs = client.list_database_names()
    if db_name not in existing_dbs:
        print(f"Database '{db_name}' does NOT exist.")
        return client[db_name] # create new db

    print(f"Database '{db_name}' exists.")
    return client[db_name]
