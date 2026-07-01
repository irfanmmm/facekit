import re
from model.database import get_database
from datetime import datetime, timedelta
from model.database import exclude
from utility.settings import Settings
from model.compony_model import ComponyModel
from connection.officekit_onboarding import OnboardingOfficekit

def list_componys(company_id=None):
    client = get_database()  # this returns a MongoClient instance

    # Fetch all DB names except excluded ones
    all_dbs = client.list_database_names()
    companies_dbs = [db_name for db_name in all_dbs if db_name not in exclude]

    result = []

    for db_name in companies_dbs:
        db = client[db_name]  # do NOT overwrite the client
        collection = db.get_collection("compony_details")

        # Fetch specific company OR all companies
        if company_id:
            docs = list(collection.find(
                {"compony_code": str(company_id)}, {"_id": 0}))
        else:
            docs = list(collection.find({}, {"_id": 0}))

        # Add default values
        for doc in docs:
            doc["status"] = doc.get("status", "pending")
            doc["compony_code"] = str(doc.get("compony_code"))
            # helpful for knowing which company DB it came from
            doc["db_name"] = db_name
            result.append(doc)

    return result


def update_client_status(compony_code, status):
    client = get_database()  # MongoClient

    all_dbs = client.list_database_names()
    companies_dbs = [db_name for db_name in all_dbs if db_name not in exclude]

    updated_user = None
    target_db_name = None

    # Find the company DB that contains this company_code
    for db_name in companies_dbs:
        db = client[db_name]
        collection = db.get_collection("compony_details")

        # Check if the company exists in this DB
        user_details = collection.find_one({"compony_code": str(compony_code)})
        if user_details:
            # Update status
            target_db_name = db_name
            collection.update_one(
                {"compony_code": str(compony_code)},
                {"$set": {"status": status}},
                upsert=True
            )
            # Refresh after update
            updated_user = collection.find_one(
                {"compony_code": str(compony_code)})
            break

    # If not found in any DB
    if not updated_user:
        return {"error": "Company code not found"}
    

    if status == "rejected" and target_db_name:
        client.drop_database(target_db_name)
        return {
            "status": "rejected",
            "message": f"Database '{target_db_name}' deleted successfully"
        }

    # Send email
    to_email = updated_user.get("email")
    password = updated_user.get("password")
    compony_url = updated_user.get("compony_url", "")

    from helper.trigger_mail import send_mail_with_template
    send_mail_with_template(
        to_email,
        to_email,
        password,
        str(compony_code),
        compony_url
    )

    return True


import base64
import glob
import os

def fech_client_details(compony_code, limit=10, offset=0, date=None):
    client = get_database(compony_code)
    collection = client.get_collection(f"encodings_{compony_code}")

    attendance_map = {}

    if date:
        try:
            year_month = date[:7]
            att_coll_name = f"attandance_{compony_code}_{year_month}"

            att_coll = client[att_coll_name]

            search_date = datetime.strptime(date, "%Y-%m-%d")

            att_records = list(
                att_coll.find(
                    {
                        "date": {
                            "$gte": search_date,
                            "$lt": search_date + timedelta(days=1)
                        }
                    },
                    {"_id": 0}
                )
            )

            attendance_map = {
                r["employee_id"]: r
                for r in att_records
                if "employee_id" in r
            }

        except Exception as e:
            print(f"Error fetching attendance: {e}")

    query = {}

    if date:
        query["employee_code"] = {
            "$in": list(attendance_map.keys())
        }

    total_count = collection.count_documents(query)

    emp_details = list(
        collection.find(
            query,
            {
                "_id": 0,
                "encodings": 0,
                "existing_user_officekit": 0,
                "company_code": 0
            }
        )
        .skip(offset)
        .limit(limit)
    )

    # ----------------------------------
    # Load images only once
    # ----------------------------------

    image_map = {}

    try:
        upload_dir = "face_match/uploads"

        if os.path.exists(upload_dir):
            all_files = os.listdir(upload_dir)

            for filename in all_files:
                full_name = filename.lower()

                for emp in emp_details:
                    emp_code = str(
                        emp.get("employee_code", "")
                    ).lower()

                    if emp_code and emp_code in full_name:
                        image_map[emp_code] = filename

    except Exception as e:
        print(f"Image loading error: {e}")

    # ----------------------------------
    # OfficeKit
    # ----------------------------------

    office_kit = OnboardingOfficekit(compony_code)

    branch_cache = {}
    agency_cache = {}

    # ----------------------------------
    # Employee Processing
    # ----------------------------------

    for emp in emp_details:

        emp_code = str(
            emp.get("employee_code", "")
        ).lower()

        emp["image"] = image_map.get(emp_code)

        if date:
            emp["attendance"] = attendance_map.get(
                emp.get("employee_code"),
                {}
            )

        branch = emp.get("branch")

        if branch and (
            isinstance(branch, int)
            or str(branch).isdigit()
        ):

            branch_key = str(branch)

            if branch_key not in branch_cache:

                try:
                    branch_data = office_kit.get_branch(
                        search=branch
                    )

                    if (
                        branch_data
                        and branch_data.get("data")
                    ):
                        branch_cache[branch_key] = (
                            branch_data["data"][0]["branch_name"]
                        )
                    else:
                        branch_cache[branch_key] = branch

                except Exception:
                    branch_cache[branch_key] = branch

            emp["branch"] = branch_cache[branch_key]

        # ------------------------------
        # Agency
        # ------------------------------

        agency = emp.get("agency")

        if agency and (
            isinstance(agency, int)
            or str(agency).isdigit()
        ):

            agency_key = str(agency)

            if agency_key not in agency_cache:

                try:
                    agency_data = office_kit.get_agency(
                        agency
                    )

                    if agency_data:
                        agency_cache[agency_key] = (
                            agency_data[0]["agent_name"]
                        )
                    else:
                        agency_cache[agency_key] = agency

                except Exception:
                    agency_cache[agency_key] = agency

            emp["agency"] = agency_cache[agency_key]

    return {
        "data": emp_details,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }

from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_branch_ids(compony_code, search_val):
    office_kit = OnboardingOfficekit(compony_code)
    if not office_kit.conn:
        return None
    branch_resp = office_kit.get_branch(search=search_val, limit=100)
    if branch_resp and branch_resp.get("data"):
        return [b["_id"] for b in branch_resp["data"]]
    return []

@lru_cache(maxsize=128)
def get_cached_agency_ids(compony_code, search_val):
    office_kit = OnboardingOfficekit(compony_code)
    if not office_kit.conn:
        return None
    agency_resp = office_kit.get_agency(search=search_val)
    if agency_resp:
        return [a["_id"] for a in agency_resp]
    return []

def fech_client_details_search(compony_code, search, limit=10, offset=0, date=None, branch=None, agency=None, name=None, employee_code=None):
    client = get_database(compony_code)  # MongoClient
    collection = client.get_collection(f"encodings_{compony_code}")
    
    attendance_map = {}
    if date:
        try:
            year_month = date[:7]
            att_coll_name = f"attandance_{compony_code}_{year_month}"
            if att_coll_name in client.list_collection_names():
                att_coll = client[att_coll_name]
                search_date = datetime.strptime(date, "%Y-%m-%d")
                att_records = list(att_coll.find({
                    "date": {"$gte": search_date, "$lt": search_date + timedelta(days=1)}
                }, {"_id": 0}))
                attendance_map = {r['employee_id']: r for r in att_records}
        except Exception as e:
            print(f"Error fetching attendance in search: {e}")

    query_parts = []
    
    
    office_kit = OnboardingOfficekit(compony_code)
    
    if branch:
        if not (isinstance(branch, int) or re.match(r'^\d+$', str(branch))):
            branch_ids = get_cached_branch_ids(compony_code, branch)
            if branch_ids is not None:
                if branch_ids:
                    query_parts.append({"branch": {"$in": branch_ids + [str(b) for b in branch_ids]}})
                else:
                    query_parts.append({"branch": -1}) # no match
            else:
                query_parts.append({"branch": {"$regex": branch, "$options": "i"}})
        else:
            query_parts.append({"branch": branch})
            
    if agency:
        if not (isinstance(agency, int) or re.match(r'^\d+$', str(agency))):
            agency_ids = get_cached_agency_ids(compony_code, agency)
            if agency_ids is not None:
                if agency_ids:
                    query_parts.append({"agency": {"$in": agency_ids + [str(a) for a in agency_ids]}})
                else:
                    query_parts.append({"agency": -1}) # no match
            else:
                query_parts.append({"agency": {"$regex": agency, "$options": "i"}})
        else:
            query_parts.append({"agency": agency})
    if name:
        query_parts.append({"fullname": {"$regex": name, "$options": "i"}})
    if employee_code:
        query_parts.append({"employee_code": {"$regex": employee_code, "$options": "i"}})
        
    if date:
        att_ids = list(attendance_map.keys())
        query_parts.append({"employee_code": {"$in": att_ids}})
        
    query = {}
    if query_parts:
        if len(query_parts) == 1:
            query = query_parts[0]
        else:
            query = {"$and": query_parts}
            
    total_count = collection.count_documents(query)
    cursor = collection.find(query, {"_id": 0, "encodings": 0, "existing_user_officekit":0, "company_code":0}).skip(offset).limit(limit)
    
    emp_details = list(cursor)
    office_kit = OnboardingOfficekit(compony_code)
    for emp in emp_details:
        emp_code = emp.get('employee_code')
        emp["image"] = None
        if emp_code:
            # Search for any file in uploads that contains the employee code
            matches = glob.glob(f"face_match/uploads/*{emp_code}*.jpg")
            if matches:
                emp["image"] = os.path.basename(matches[0])
        
        # Attach attendance info if date was provided
        if date:
            emp["attendance"] = attendance_map.get(emp_code, {})

        branch = emp.get('branch')
        if branch and (isinstance(branch, int) or re.match(r'^\d+$', str(branch))):
            branch_data = office_kit.get_branch(search=branch)
            if branch_data and branch_data.get('data'):
                emp['branch'] = branch_data['data'][0]['branch_name']

    return {
        "data": emp_details,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "search": search
    }


def create_company(data):
    if not data:
        return jsonify({"error": "No JSON body received"}), 400

    compony_name = data.get("compony_name")
    _name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    mobile_no = data.get("mobile_no")
    emp_count = data.get("emp_count")
    client = data.get("client")
    if not all([compony_name, _name, email, password, mobile_no, emp_count]):
        return jsonify({"error": "Missing required fields"})

    
    componyCode = ComponyModel(client)
    message, company_code = componyCode._set(
        compony_name, _name, email, password, mobile_no, emp_count, client)
        
    if message == "faild":
        return message
    return message