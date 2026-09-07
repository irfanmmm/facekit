from model.database import get_database
from functools import lru_cache

class Settings:
    """
    Manages dynamic settings for each client.
    Supports default fallbacks and easy access via keys.
    """
    
    DEFAULT_SETTINGS = {
        "Location Tracking": False,
        "Individual Login": False,
        "Branch Management": False,
        "Agency Management": False,
        "Shift Management": False,
        "Office Kit Integration": False,
        "List Employees": False,
        "Enable Create User":False,
        "Office Kit Onboarding": False,
        "Branch Wise Login":False
    }

    def __init__(self, company_code):
        self.company_code = company_code
        self.db = get_database("SettingsDB")
        self.collection = self.db[f"settings_{company_code}"]
        self._cache = None

    def _load(self):
        """Lazy load settings into a dictionary cache"""
        if self._cache is None:
            # Fetch from DB
            docs = list(self.collection.find({}, {"_id": 0}))
            
            # Convert list of {setting_name, value} to flattened dict
            self._cache = {doc['setting_name']: doc['value'] for doc in docs if 'setting_name' in doc}
            
            # Ensure all defaults exist in the cache if not present in DB
            for name, default_value in self.DEFAULT_SETTINGS.items():
                if name not in self._cache:
                    self._cache[name] = default_value
        return self._cache

    def get(self, name, default=False):
        """Get a setting value by name"""
        settings = self._load()
        return settings.get(name, default)

    def get_all(self):
        """Get all settings as a list of dictionaries for legacy UI support"""
        settings = self._load()
        return [{"setting_name": name, "value": value} for name, value in settings.items()]

    def update(self, name, value):
        """Update or create a setting"""
        self.collection.update_one(
            {"setting_name": name},
            {"$set": {"value": value}},
            upsert=True
        )
        self._cache = None
        Settings.get_setting.cache_clear()
        return True

    @staticmethod
    @lru_cache(maxsize=128)
    def get_setting(company_code, name, default=False):
        """Quick static access to a specific setting value"""
        return Settings(company_code).get(name, default)

    
