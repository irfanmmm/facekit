from datetime import datetime, timedelta, timezone
from model.database import get_database
from dotenv import load_dotenv
from pymongo import MongoClient
import re
import os
from face_match.face_ml import EXCEPTION_SECONDS, WORKING_SECONDS
load_dotenv()


def job():
    CONNECTION_URL = os.getenv("DATABASE_URL")
    client = MongoClient(CONNECTION_URL)
    pattern = re.compile(r"^A[0-9]{2,3}$")
    db_names = client.list_database_names()
    matching_dbs = [name for name in db_names if pattern.search(name)]
    now = datetime.now(timezone.utc)
    yesterday_start = (now - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    yesterday_end = (now - timedelta(days=1)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    print(yesterday_start, yesterday_end)
    for name in matching_dbs:
        db = client[name]
        year_month = now.strftime('%Y-%m')
        collection_name = f'attandance_{name}_{year_month}'
        collection = db[collection_name]

        filter_query = {
            "date": {"$gte": yesterday_start, "$lt": yesterday_end},
            "$or": [
                {"present": {"$exists": False}},
                {"present": ""}
            ]
        }

        for data in list(collection.find(filter_query)):
            print(data)
            log_details = data.get("log_details") or []
            status = "A"
            last_item = log_details[-1] if log_details else None
            if last_item:
                working_time = data.get("total_working_time")
                including_exception = max(working_time - EXCEPTION_SECONDS, 0)
                if including_exception >= WORKING_SECONDS:
                    status = "P"
                else:

                    status = "A"
            else:
                status = "A"

            print(data)
            _user_filter = {"_id": data["_id"]}
            _update_data = {
                "present": status
            }
            
            update_count = collection.update_one(_user_filter, {"$set": _update_data})
            print("success",update_count)


if __name__ == "__main__":
    job()
