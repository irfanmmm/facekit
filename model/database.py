from pymongo import MongoClient
import os
from functools import lru_cache

# CONNECTION_URL = "mongodb://localhost:27017/"
exclude = ["SettingsDB", "admin", "sample_mflix", "local"]

_MONGO_CLIENT = None

def _get_client():
    """Singleton pattern to get the Mongo Client"""
    global _MONGO_CLIENT
    if _MONGO_CLIENT is None:
        _MONGO_CLIENT = MongoClient(
            os.getenv("DATABASE_URL"),
            maxPoolSize=50,
            minPoolSize=5,
            serverSelectionTimeoutMS=5000
        )
    return _MONGO_CLIENT

@lru_cache(maxsize=64)
def get_database(db_name=None):
    """
    Get a database instance or the client itself.
    Cached to avoid repeated dictionary lookups on the client.
    """
    try:
        client = _get_client()
        if db_name:
            return client[db_name]
        return client
    except Exception as e:
        print(f"Error in get_database: {e}")
        return False
