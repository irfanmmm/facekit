from model.database import get_database
from model.database import exclude


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
                {"compony_code": company_id}, {"_id": 0}))
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

    # Find the company DB that contains this company_code
    for db_name in companies_dbs:
        db = client[db_name]
        collection = db.get_collection("compony_details")

        # Check if the company exists in this DB
        user_details = collection.find_one({"compony_code": str(compony_code)})
        if user_details:
            # Update status
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
