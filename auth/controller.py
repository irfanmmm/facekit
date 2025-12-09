
from flask import Blueprint, app, jsonify, request

from middleware.auth_middleware import jwt_required
from model.compony_model import ComponyModel
from model.database import get_database
from utility.jwt_utils import create_token
import secrets

auth = Blueprint('auth', __name__)

""" Register user """


@auth.route('/signup', methods=['POST'])
def sighnup():
    data = request.get_json()
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

    if not client:
        from model.compony_model import ComponyModel, generate_code
        client = generate_code()
    componyCode = ComponyModel(client)
    message, company_code = componyCode._set(
        compony_name, _name, email, password, mobile_no, emp_count, client)
    if message == "faild":
        return jsonify({"message": company_code})
    return jsonify({"message": message})


@auth.route("/verify-compony-code", methods=['POST'])
def verify_compony_code():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    compony_code = data.get("code")
    if not compony_code:
        return jsonify({"message": "compony code is requerd"})
    componyCode = ComponyModel(compony_code)
    message, token = componyCode._verify(compony_code)
    if message == "success":
        return jsonify({"message": message, "token": token})

    return jsonify({"message": message})


""" individual user | admin login """


@auth.route("/user-login", methods=['POST'])
@jwt_required
def login_user():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    username = data.get("username")
    password = data.get("password")
    compony_code = user.get('compony_code')
    if not all([username, password]):
        return jsonify({"message": "Missing required fields"})
    db = get_database(compony_code)
    collection = db["compony_details"]
    admin_user = collection.find_one(
        {"compony_code": user.get('compony_code')}, {"_id": 0})
    admin_user.get("password", "")
    admin_user.get("email", "")

    if admin_user.get("email") == username and admin_user.get("password") == password:
        token = create_token({"compony_code": compony_code,
                             "is_admin": True, "settings": user.get("settings")})
        return jsonify({"message": "success", "token": token})

    emp_collection = db[f'encodings_{compony_code}']
    if emp_collection.find_one(
            {"company_code": compony_code, "employee_code": username, "password": password}, {"_id": 0}):
        token = create_token({"compony_code": compony_code,
                             "is_admin": False, "employee_code": username, "settings": user.get("settings")})
        return jsonify({"message": "success", "token": token})
    return jsonify({"message": "Failed"})


"""individual syastem admin add user without add face and password """

@auth.route("/add-employee", methods=['POST'])
@jwt_required
def add_user_in_admin():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    email = data.get("email")
    employeecode = data.get("employeecode")
    if not all([email, employeecode]):
        return jsonify({"message": "Missing required fields"})

    branch_settings = user.get("settings")
    if branch_settings:
        branch_found = False
        individual_login = False
        agency_management_enabled = False
        for setting in branch_settings:
            if setting.get("setting_name") == "Branch Management":
                value = setting.get("value", False)
                if not value:
                    break
                user_branch = data.get("branch")
                if not user_branch:
                    return jsonify({"message": "Branch name is requerd"})
                db = get_database(user.get("compony_code"))
                branch_detail = db[f'branch_{user.get("compony_code")}']
                if not branch_detail.find_one({"compony_code": user.get("compony_code"), "branch_name": user_branch}):
                    return jsonify({"message": "Invalid branch name"})
                branch_found = True
            if setting.get("setting_name") == "Individual Login":
                individual_login = setting.get("value", False)
            if setting.get("setting_name") == "Agency Management":
                agency_management_enabled = setting.get("value", False)
                agency = data.get("agency")
                if not agency and agency_management_enabled:
                    return jsonify({"message": "agency is requerd"}), 400

        db = get_database(user.get("compony_code"))
        compony_details = db[f'compony_details']
        if not compony_details.find_one({"compony_code": user.get("compony_code"), "status": "active"}):
            return jsonify({"message": "Invalid company code or inactive company"})
        collection = db[f'encodings_{user.get("compony_code")}']

        doc = {
            "company_code": user.get("compony_code"),
            "employee_code": employeecode,
            "email": email
        }

        # Add conditions safely
        if branch_found:
            doc["branch"] = user_branch

        if agency_management_enabled:
            doc["agency"] = agency

        # Insert only once
        collection.insert_one(doc)
        #     collection.insert_one({"company_code": user.get(
        #         "compony_code"), "employee_code": employeecode,  "email": email, "agency": agency})
        # if agency_management_enabled and branch_found:
        #     collection.insert_one({"company_code": user.get(
        #         "compony_code"), "employee_code": employeecode,  "email": email, "branch": user_branch, "agency": agency})
        # if not branch_found and not agency_management_enabled:
        # collection.insert_one({"company_code": user.get(
        #     "compony_code"), "employee_code": employeecode,  "email": email})

        if individual_login:
            from helper.trigger_mail import send_mail_with_template
            generated_password = secrets.token_urlsafe(10)
            send_mail_with_template(to_email=email, username=employeecode,
                                    password=generated_password, company_code=user.get("compony_code"), confirm_url="")
        return jsonify({"message": "success"})
    return jsonify({"message": "Failed"})


@auth.route("/create-password", methods=['POST'])
@jwt_required
def create_password():
    user = request.user
    data = request.get_json()
    compony_code = user.get("compony_code")
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    employeecode = data.get("employeecode")
    password = data.get("password")
    if not all([employeecode, password]):
        return jsonify({"message": "Missing required fields"})

    db = get_database(compony_code)
    collection = db[f'encodings_{compony_code}']
    result = collection.update_one(
        {"company_code": compony_code,
         "employee_code": employeecode},
        {"$set": {"password": password}}
    )
    if result.matched_count == 0:
        return jsonify({"message": "Employee not found"})
    return jsonify({"message": "success"})


""" common admin verify """


@auth.route("/verify-admin", methods=['POST'])
@jwt_required
def verify_admin():
    user = request.user
    data = request.get_json()
    compony_code = user.get("compony_code")
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    username = data.get("username")
    password = data.get("password")

    if not all([username, password]):
        return jsonify({"message": "Missing required fields"})

    componyCode = ComponyModel(compony_code)
    message = componyCode._verify_admin(
        user.get("compony_code"), username, password)
    return jsonify({"message": message})


""" generate employee code """


@auth.route("/generate-employee-code", methods=['GET'])
@jwt_required
def generate_employee_code():
    user = request.user
    compony_code = user.get("compony_code")
    componyCode = ComponyModel(compony_code)
    emp_code = componyCode._generate_employee_code(user.get("compony_code"))
    return jsonify({"message": "success", "employee_code": emp_code})


@auth.route("/refresh-token", methods=['GET'])
@jwt_required
def refresh_toke():
    user = request.user
    new_token = create_token(user)
    return jsonify({"message": "success", "token": new_token})
