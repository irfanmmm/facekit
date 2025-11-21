from model.database import get_database
setting = [
    {
        "setting_name": "Location Tracking",
        "value": False
    },
    {
        "setting_name": "Individual Login",
        "value": False
    },
    {
        "setting_name": "Branch Management",
        "value": False
    },
    {
        "setting_name": "Agency Management",
        "value": False
    },
    {
        "setting_name": "Office Kit Integration",
        "value": False
    },
]


def list_settings(compony_code):
    db = get_database("SettingsDB")
    collection = db[f"settings_{compony_code}"]
    settings_data = collection.find({}, {"_id": 0}).to_list()
    if len(settings_data) > 0:
        return settings_data
    else:
        collection.insert_many(setting)
        setting.pop("_id", None)
        return setting


def update_settings(compony_code, new_settings, value):
    db = get_database("SettingsDB")
    collection = db[f"settings_{compony_code}"]
    collection.update_one(
        {"setting_name": new_settings},
        {"$set": {"value": value}},
        upsert=True)
    return True
