from model.database import get_database


def list_componys(id=None):
    db = get_database()
    collections = db['compony_details']
    if id:
        companies = collections.find(
            {"compony_code": id}, {"_id": 0}).to_list()
    else:
        companies = collections.find({}, {"_id": 0}).to_list()
    for item in companies:
        item["status"] = item.get("status", "pending")
        item['compony_code'] = str(item['compony_code'])
    return companies


def update_client_status(compony_code, status):
    db = get_database()
    collections = db['compony_details']
    collections.update_one(
        {"compony_code": str(compony_code)},
        {"$set": {"status": status}},
        upsert=True
    )
    user_details = collections.find_one({"compony_code": str(compony_code)})

    to_email = user_details.get("email")
    password = user_details.get("password")
    compony_url = user_details.get("compony_url", "")
    from helper.trigger_mail import send_mail_with_template
    send_mail_with_template(to_email, to_email, password,
                            str(compony_code), compony_url)
    return True
