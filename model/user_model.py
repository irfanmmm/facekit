import os
from pydoc import doc
from model.database import get_database
from datetime import datetime, timedelta
from face_match.face_ml import FaceAttendance
from face_match.faiss_manager import FaceIndexManager
import numpy as np
# import datetime

# def is_sunday(year):
#     sundays = []
#     # Start from January 1st
#     date = datetime.date(year, 1, 1)
#     # Loop through each day of the year
#     while date.year == year:
#         if date.weekday() == 6:  # Sunday is 6
#             sundays.append(date)
#         date += datetime.timedelta(days=1)
#     return sundays


class UserModel():
    def __init__(self, compony_code):
        self.db = get_database(compony_code)

    def get_all_users(self, compony_code, limit, offset, search=None):
        collection = self.db[f'encodings_{compony_code}']

        base_filter = {"is_delete": {"$ne": True}}

        if search:
            search_filter = {
                "$or": [
                    {"employee_code": {"$regex": search, "$options": "i"}},
                    {"fullname": {"$regex": search, "$options": "i"}},
                ]
            }

            query = {"$and": [base_filter, search_filter]}
        else:
            query = base_filter

        cursor = (
            collection.find(query, {"_id": 0, "encodings": 0})
            .skip(offset)
            .limit(limit)
        )

        total = collection.count_documents(query)

        return {
            "data": cursor.to_list(length=limit),
            "limit": limit,
            "offset": offset,
            "total": total
        }

    def edit_user_details(self, compony_code, editable_details, base64=None):
        available_actions = ['E', 'D']

        if not isinstance(editable_details, dict) or not editable_details:
            return "editable_details must be a non-empty list"

        action = editable_details['action']

        if action in available_actions:
            db = get_database(compony_code)
            collection = db[f'encodings_{compony_code}']
            user_id = editable_details.get('employee_code')
            user = collection.find_one(
                {"employee_code": user_id})
            if not user:
                return "Employee not exist"

            if action == 'E':
                if base64:
                    face_details = FaceAttendance()
                    status, message = face_details.edit_employee_face(
                        employee_code=editable_details['employee_code'],
                        emp_face=base64,
                        compony_code=compony_code,
                    )
                    if not status:
                        return message

                branch = editable_details.get('branch', None)
                agency = editable_details.get('agency', None)
                fullname = editable_details.get('full_name', None)

                _filter = {
                    "_id": user.get("_id"),
                }
                result = collection.update_one(_filter, {
                    "$set": {
                        "company_code": compony_code,
                        "employee_code": user_id,
                        "branch": branch,
                        "agency": agency,
                        "fullname": fullname
                    }
                })

                if result.matched_count == 0:
                    return "No document found to update"

                return "success"

            if action == "D":
                _filter = {
                    "_id": user.get("_id"),
                }
                result = collection.update_one(_filter, {
                    "$set": {
                        "is_delete": True,
                        "encodings": None
                    }
                })
                if result.matched_count == 0:
                    return "No document found to update"
                cache = FaceIndexManager(compony_code)
                cache.rebuild_index()
                return "success"
        return "Somthing went wrong"

    def edit_attandance_report(self, compony_code, emploee_list_with_action, editad_date):
        """ [{'employee_id':'1','action':'P' | 'PL' | 'UL' | 'H'}] """

        remarks = ['P', 'PL', 'UL', 'H']
        for emploee_dict in emploee_list_with_action:
            if emploee_dict['action'] not in remarks:
                return "action not available"
            colloction = self.db[f"attandance_{compony_code}_{datetime.utcnow().strftime('%Y-%m')}"]
            starting_at = datetime.strptime(editad_date, "%Y-%m-%d")
            ending_at = datetime.strptime(
                editad_date, "%Y-%m-%d") + timedelta(days=1)
            _filter = {"employee_id": emploee_dict['employee_code'], "date": {
                "$gte": starting_at, "$lt": ending_at}}

            colloction.update_one(_filter, {
                "$set": {
                    "present": emploee_dict['action'],
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {
                    "employee_id": emploee_dict['employee_code'],
                    "fullname": emploee_dict.get('employee_name'),
                    "total_working_time": 0,
                    "date": starting_at,
                    "company_code": compony_code,
                    "created_at": datetime.utcnow(),
                    "log_details": []
                }
            }, upsert=True)
            print("success")
        return "success"

    def get_attandance_report(self, compony_code, employee_code, starting_date, ending_date):
        # collection = self.db[f'attandance_{compony_code}']
        collection = self.db[f"attandance_{compony_code}_{datetime.utcnow().strftime('%Y-%m')}"]
        # 2025-10-01 formate
        starting_at = datetime.strptime(starting_date, "%Y-%m-%d")
        ending_at = datetime.strptime(
            ending_date, "%Y-%m-%d") + timedelta(days=1)
        _filter = {"employee_id": employee_code, "date": {
            "$gte": starting_at, "$lt": ending_at}}
        employee_log_list = collection.find(
            _filter, {"_id": 0, "log_details": 0}).to_list()
        return employee_log_list

    def get_attandance_report_all(self, compony_code, starting_date, ending_date, limit, offset, search=None):
        db = self.db
        start = datetime.strptime(starting_date, "%Y-%m-%d")
        end = datetime.strptime(ending_date, "%Y-%m-%d")

        end = end + timedelta(days=1)

        all_results = []

        current = start.replace(day=1)

        while current <= end:
            month_key = current.strftime("%Y-%m")
            collection_name = f"attandance_{compony_code}_{month_key}"
            collection = db[collection_name]
            month_start = max(start, current)
            next_month = (current.replace(day=28) +
                          timedelta(days=4)).replace(day=1)
            month_end = min(end, next_month)

            try:
                query = {}
                if search:
                    query = {
                        "$or": [
                            {"employee_code": {"$regex": search, "$options": "i"}},
                            {"fullname": {"$regex": search, "$options": "i"}},
                        ]
                    }
                cursor = (
                    db[f"encodings_{compony_code}"].find(
                        query, {"_id": 0, "encodings": 0})
                    .skip(offset)
                    .limit(limit)
                )
                existing_users = cursor.to_list(length=limit)
                total_count = db[f"encodings_{compony_code}"].count_documents(
                    query)

                for user in existing_users:
                    _filter = {"date": {
                        "$gte": month_start, "$lt": month_end}, "employee_id": user['employee_code']}
                    cursor = collection.find_one(
                        _filter, {"_id": 0, "log_details": 0})
                    if cursor:
                        all_results.append(cursor)
                    else:
                        all_results.append({
                            "employee_id": user['employee_code'],
                            "fullname": user['fullname'],
                            "company_code": compony_code,
                            "date": None,
                            "total_working_time": 0,
                            "present": "A",
                            "log_details": []
                        })
            except Exception:
                pass

            current = next_month

        return {"data": all_results, "total": total_count, "limit": limit, "offset": offset}

    def find_duplicate_faces(self, company_code: str, threshold: float = 0.40):
        db = self.db
        collection = db[f'encodings_{company_code}']

        docs = list(collection.find(
            {},
            {"_id": 1, "employee_code": 1, "encodings": 1}
        ))

        cache = FaceIndexManager(company_code)
        if cache.index is None:
            cache.rebuild_index()

        seen_pairs = set()
        duplicates = {}

        for doc in docs:
            enc_list = doc.get("encodings")

            if not enc_list or len(enc_list) != 128:
                continue
            emp_code = doc["employee_code"]
            enc = np.array(doc["encodings"],
                       dtype=np.float32).reshape(1, -1)

            results = cache.search(enc,k=10, threshold=0.40)

            for res in results:
                matched_emp = res["employee"]["employee_code"]

                if matched_emp == emp_code:
                    continue

                # # 2️⃣ Avoid A↔B double counting
                # pair = tuple(sorted([emp_code, matched_emp]))
                # if pair in seen_pairs:
                #     continue
                # seen_pairs.add(pair)

                duplicates.setdefault(emp_code, []).append({
                    "matched_employee": matched_emp,
                    "distance": res["distance"]
                })

        return duplicates
