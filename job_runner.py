from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import csv
import io
import re

from face_match.face_ml import WORKING_SECONDS
from helper.format_duration import format_duration

load_dotenv()

GRACE_SECONDS = 5 * 60
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def job():
    CONNECTION_URL = os.getenv("DATABASE_URL")
    client = MongoClient(CONNECTION_URL)

    pattern = re.compile(r"^A[0-9]{2,3}$")
    db_names = client.list_database_names()
    matching_dbs = [name for name in db_names if pattern.search(name)]

    now = datetime.now(timezone.utc)

    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end   = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)


    for name in matching_dbs:
        db = client[name]
        year_month = (now - timedelta(days=1)).strftime("%Y-%m")
        collection = db[f"attandance_{name}_{year_month}"]
        usercollection = db[f"encodings_{name}"]

        filter_query = {
            "date": {"$gte": yesterday_start, "$lte": yesterday_end},
            "$or": [{"present": {"$exists": False}}, {"present": ""}]
        }

        for data in collection.find(filter_query):
            log_details = data.get("log_details") or []
        
            log_details = data.get("log_details", [])
            total_working = data.get("total_working_time") or 0
            if not log_details:
                status = "A"
            elif len(log_details) == 1:
                status = "A"
            elif total_working == 0:
                status = "A"
            elif total_working <= WORKING_SECONDS:
                status = "A"
            else:
                status = "P"
                
            _filter_user_details = {
                **filter_query,
                "employee_id":data.get("employee_id"),
            }
            result = collection.update_one(_filter_user_details, {"$set": {"present": status, "updatedAt": datetime.now()}})

if __name__ == "__main__":
    job()
