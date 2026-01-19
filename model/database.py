from pymongo import MongoClient
import os

# CONNECTION_URL = "mongodb://localhost:27017/"
exclude = ["SettingsDB", "admin", "sample_mflix", "local"]
from pymongo import MongoClient
import os

_MONGO_CLIENT = None

def get_database(db_name=None):
    try:
        global _MONGO_CLIENT

        if _MONGO_CLIENT is None:
            _MONGO_CLIENT = MongoClient(
                os.getenv("DATABASE_URL"),
                maxPoolSize=50,
                minPoolSize=5,
                serverSelectionTimeoutMS=5000
            )

        if db_name:
            return _MONGO_CLIENT[db_name]

        return _MONGO_CLIENT
    except Exception as e:
            print(f"Error inserting branch: {e}")
            return False
