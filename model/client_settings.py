from model.database import get_database
from datetime import datetime
from pymongo import IndexModel, ASCENDING

class ClientSettingsModel:
    def __init__(self):
        self.db = get_database("SettingsDB")
        self.collection = self.db["client_settings"]
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.collection.create_index([("client_id", ASCENDING)], unique=True)

    def get_settings(self, client_id):
        return self.collection.find_one({"client_id": client_id}, {"_id": 0})

    def update_settings(self, client_id, data):
        data["updated_at"] = datetime.utcnow()
        return self.collection.update_one(
            {"client_id": client_id},
            {"$set": data},
            upsert=True
        )

    def create_default_settings(self, client_id):
        default_settings = {
            "client_id": client_id,
            "attendance_flow": ["face"],
            "features": {
                "face_recognition": True,
                "liveness": False,
                "geo_fencing": False
            },
            "rules": {
                "require_liveness_if_confidence_below": 0.7,
                "allow_multiple_faces": False
            },
            "face_threshold": 0.6,
            "new_feature": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        self.collection.update_one(
            {"client_id": client_id},
            {"$setOnInsert": default_settings},
            upsert=True
        )
        return default_settings
