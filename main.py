import logging
import os
import time
import schedule
import json
from flask import Flask, render_template, request, jsonify, g
from face_match.face_ml import FaceAttendance
from middleware.auth_middleware import jwt_required
from model.compony_model import ComponyModel
from model.user_model import UserModel
from connection.validate_officekit import Validate
from connection.db_officekit import conn, cursor
from face_match import init_faiss_indexes
from admin.controller import admin
from auth.controller import auth
from attandance.controller import attandance
from datetime import datetime, timezone, timedelta
from model.database import get_database
from logging.handlers import RotatingFileHandler


IST = timezone(timedelta(hours=5, minutes=30))


def now_ist_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"


app = Flask(__name__, template_folder='public/templates')
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(attandance, url_prefix="/attandance")

log_path = "logs/facekit.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Use app.logger
app_logger = app.logger
app_logger.setLevel(logging.INFO)


@app.before_request
def log_request_body():
    ip = request.access_route[0] if request.access_route else request.remote_addr
    if request.content_type and "multipart/form-data" in request.content_type:
        pass
    else:
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {request.get_data()}")


@app.after_request
def after_request(response):
    try:
        # Calculate duration
        start_time = g.start_time
        duration = time.time() - start_time
    except Exception:
        duration = 0

    # Get response data (decode from bytes)
    try:
        response_data = response.get_data(as_text=True)
    except Exception:
        response_data = "<unable to read response>"
    app.logger.info(
        f"RESPONSE | {request.method} {request.path} | STATUS: {response.status_code} "
        f"| TIME: {duration}s | BODY: {response_data}"
    )
    return response


OFFICE_KIT_API_KEY = "wba1kit5p900egc12weblo2385"
OFFICE_KIT_PRIMERY_URL = "http://appteam.officekithr.net/api/AjaxAPI/MobileUrl"

# ---------------- DB Connection ----------------

attendance = FaceAttendance()


@app.route("/add-branch", methods=['POST'])
@jwt_required
def add_branch():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    branch_name = data.get('branch_name')

    for setting in user.get("settings"):
        if setting.get("setting_name") == "Location Tracking":
            if setting.get("value", False):
                if not data.get('latitude') or not data.get('longitude') or not data.get('radius'):
                    return jsonify({"message": "latitude, longitude and radius are required"})

            latitude = data.get('latitude', None)
            longitude = data.get('longitude', None)
            radius = data.get("radius", None)

    componyCode = ComponyModel(compony_code)
    status = componyCode._branch_set(
        compony_code, branch_name, latitude, longitude, radius)
    if status:
        return jsonify({"message": "success"})
    return jsonify({"message": "Failed"})


@app.route("/get-branch")
@jwt_required
def get_branches():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    branches = componyCode._get_branch(
        compony_code)
    if branches:
        return jsonify({"message": "success", "details": branches})
    return jsonify({"message": "Failed"})


@app.route("/get-agency")
@jwt_required
def get_agencys():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    agencys = componyCode._get_agents(
        compony_code)
    if agencys:
        return jsonify({"message": "success", "details": agencys})
    return jsonify({"message": "Failed"})


@app.route("/set-agency", methods=['POST'])
@jwt_required
def set_branches():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    agency = data.get('agency')
    if not agency:
        return jsonify({"message": "agency is requerd"})
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    agencys = componyCode._set_agents(
        compony_code, agency)
    if agencys:
        return jsonify({"message": "success"})
    return jsonify({"message": "Failed"})


@app.route("/add-employee-face", methods=['POST'])
@jwt_required
def add_employee_face():
    user = request.user
    if 'file' in request.files:
        data = request.form
        file = request.files.get('file')
        fullname = data.get('fullname')
        employeecode = data.get('employeecode')
        compony_code = user.get('compony_code')

        branch_requerd = False
        for settings in user.get("settings", []):
            if settings.get("setting_name") == "Branch Management":
                branch_requerd = settings.get("value", False)
                branch = data.get('branch')
                if branch_requerd and not branch:
                    return jsonify({"message": "Branch is requerd"})
            if settings.get("setting_name") == "Agency Management":
                agency_requerd = settings.get("value", False)
                agency = data.get('agency')
                if agency_requerd and not agency:
                    return jsonify({"message": "Agency is requerd"})

        if not all([fullname, employeecode, compony_code]):
            return jsonify({"error": "Missing required fields"})
        validate = Validate(compony_code, employeecode,
                            isAdmin=user.get("is_admin", False))
        validate_user, user = validate.validate_employee()
        if validate_user:
            return jsonify({"message": "User already exists in Face Database"})
        status, message = attendance.update_face(
            employee_code=employeecode, branch=branch, agency=agency, add_img=file, company_code=compony_code, fullname=fullname, existing_office_kit_user=user)
        if status:
            return jsonify({"message": "success"})
        return jsonify({"message": "Failed" if not message else message})
    return jsonify({"message": "file is missing"})


@app.route("/compare-face", methods=['POST'])
@jwt_required
def comare_face():
    user = request.user
    if 'file' not in request.files:
        return jsonify({"message": "File is missing"}), 200

    file = request.files['file']

    location_settings = False
    individual_login = False
    officekit_user = False
    for settings in user.get("settings", []):
        if settings.get("setting_name") == "Location Tracking":
            location_settings = settings.get("value", False)
        elif settings.get("setting_name") == "Individual Login":
            individual_login = settings.get("value", False)
        elif settings.get("setting_name") == "Office Kit Integration":
            officekit_user = settings.get("value", False)

    if location_settings:
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        left = request.form.get('left')
        right = request.form.get('right')
        bottom = request.form.get('bottom')
        top = request.form.get('top')
        width = request.form.get('width')
        height = request.form.get('height')

        if not all([latitude, longitude, left, right, top, bottom, width, height]):
            return jsonify({"message": "Missing data"}), 200
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except:
            return jsonify({"message": "Invalid location"}), 200

        face_paramiter = (int(left), int(right), int(top),
                          int(bottom), int(width), int(height))

        success, result = attendance.compare_faces(
            base_img=file,
            company_code=user.get("compony_code"),
            latitude=latitude,
            longitude=longitude,
            # face_paramiter=face_paramiter
        )

        if success:
            return jsonify({"message": "success", "details": result}), 200
        else:
            return jsonify({"message": result}), 200
    else:
        success, result = attendance.compare_faces(
            base_img=file,
            company_code=user.get("compony_code"),
            latitude=None,
            longitude=None,
            individual_login=individual_login,
            officekit_user=officekit_user
        )

        if success:
            return jsonify({"message": "success", "details": result}), 200
        else:
            return jsonify({"message": result}), 200


@app.route("/all-employees", methods=['POST'])
@jwt_required
def all_employees():
    user = request.user
    data = request.get_json()
    # if not data:
    #     return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    limit = data.get('limit')
    offset = data.get('offset')
    search = data.get('search') if data.get('search') else None
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    if not limit:
        limit = 10
    if not offset:
        offset = 0
    userdetails = UserModel(compony_code)
    data = userdetails.get_all_users(
        compony_code=compony_code, limit=limit, offset=offset, search=search)
    return jsonify({"message": "success", "data": data})


@app.route("/attandance-report", methods=['POST'])
@jwt_required
def attandance_report():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    employee_code = data.get('employee_code')
    if not employee_code:
        return jsonify({"message": "employee_code is requerd"})

    starting_date = data.get('starting_date')
    if not starting_date:
        return jsonify({"message": "starting_date is requerd"})

    ending_date = data.get('ending_date')
    if not ending_date:
        return jsonify({"message": "ending_date is requerd"})

    userdetails = UserModel(compony_code)
    data = userdetails.get_attandance_report(
        compony_code=compony_code, employee_code=employee_code, starting_date=starting_date, ending_date=ending_date)
    return jsonify({"message": "success", "data": data})


@app.route("/attandance-report-all", methods=['POST'])
@jwt_required
def attandance_report_all():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    starting_date = data.get("starting_date")
    ending_date = data.get("ending_date")
    if not all([starting_date, ending_date]):
        return jsonify({"message": "date is requerd"})
    limit = user.get('limit')
    offset = user.get('offset')
    search = user.get('search') if user.get('search') else None
    if not limit:
        limit = 10
    if not offset:
        offset = 0

    
    userdetails = UserModel(compony_code)
    data = userdetails.get_attandance_report_all(
        compony_code=compony_code, starting_date=starting_date, ending_date=ending_date, limit=limit, offset=offset, search=search)
    return jsonify({"message": "success", "data": data})


@app.route("/edit-attandance", methods=['POST'])
@jwt_required
def edit_attandance():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    # employee_code = data.get('employee_code')

    """ [{'employee_id':'1','action':'P' | 'PL' | 'UL' | 'H'}] """
    editable_details = data.get("editable_details")
    if not editable_details:
        return jsonify({"message": "editable_details is requerd"})

    editad_date = data.get("date")
    if not editad_date:
        return jsonify({"message": "editad_date is requerd"})

    userdetails = UserModel(compony_code)
    message = userdetails.edit_attandance_report(
        compony_code=compony_code, emploee_list_with_action=editable_details, editad_date=editad_date)
    if message:
        return jsonify({"message": message})
    return jsonify({"message": "Failed"})


@app.route("/edit-user", methods=['POST'])
@jwt_required
def edit_user():
    data = request.form
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    editable_details_raw = data.get("editable_details")
    editable_details = json.loads(
        editable_details_raw) if editable_details_raw else []
    editable_details_files = []
    for i, emp in enumerate(editable_details):
        editable_details_files.append({
            "employee_id": emp['employee_code'],
            "branch": emp["branch"],
            "action": emp['action'],
            "full_name": emp['full_name'] if emp['full_name'] else None,
            "file": request.files.get(f"file_{i}") if request.files.get(f"file_{i}") else None
        })
    if editable_details_files:
        userdetails = UserModel(compony_code)
        message = userdetails.edit_user_details(
            compony_code, editable_details_files)
        return jsonify({"message": message})
    return jsonify({"message": "Failed"})


@app.route("/logs", methods=['POST'])
@jwt_required
def get_logs():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    page = data.get("page")
    limit = data.get("limit")
    counts, data = attendance.get_logs(
        compony_code, from_date, to_date, page=page, limit=limit)
    return jsonify({"message": "success", "counts": counts, "data": data})


@app.route("/app-version", methods=['GET'])
def app_version():
    db = get_database("AppVersion")

    # Check if collection exists
    if "appversion" not in db.list_collection_names():
        db.create_collection("appversion")

    collection = db["appversion"]

    version = collection.find_one({}, {"_id": 0})
    return jsonify({"message": "success", "version": version})


@app.route('/')
def home():
    return "Welcome to AttendEase API"


if __name__ == "__main__":
    init_faiss_indexes()

    # db = get_database("A941")
    # collection = db[f'encodings_A941']
    # pipeline = [
    #     {
    #         "$group": {
    #             "_id": "$employee_code",
    #             "count": {"$sum": 1},
    #             "docs": {"$push": "$$ROOT"}
    #         }
    #     },
    #     {
    #         "$match": {
    #             "count": {"$gt": 1}  # Only duplicates
    #         }
    #     },
    #     { "$unwind": "$docs" },
    #     { "$replaceRoot": { "newRoot": "$docs" } }
    # ]

    # duplicates = list(collection.aggregate(pipeline))
    # # for doc in duplicates:
    # print(duplicates, "duplicatesduplicatesduplicates")
    app.run(debug=True, port=5001, host="0.0.0.0")
