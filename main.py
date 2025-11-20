import logging
import os
import time
import schedule
import json
from flask import Flask, render_template, request, jsonify
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

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"


app = Flask(__name__, template_folder='public/templates')
app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(attandance, url_prefix="/attandance")


log_path = r"logs\face_comparison.log"

os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

print("Logging file created at:", log_path)


OFFICE_KIT_API_KEY = "wba1kit5p900egc12weblo2385"
OFFICE_KIT_PRIMERY_URL = "http://appteam.officekithr.net/api/AjaxAPI/MobileUrl"

# ---------------- DB Connection ----------------

attendance = FaceAttendance()  # initialize once
componyCode = ComponyModel()  # initialize once
userdetails = UserModel()

logger = logging.getLogger(__name__)


@app.route("/add-branch", methods=['POST'])
@jwt_required
def add_branch():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    branch_name = data.get('branch_name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    radius = data.get("radius")
    if not all([branch_name, latitude, longitude, compony_code, radius]):
        return jsonify({"error": "Missing required fields"})
    status = componyCode._branch_set(
        compony_code, branch_name, latitude, longitude, radius)
    if status:
        return jsonify({"message": "success"})
    return jsonify({"message": "Falid"})


@app.route("/get-branch")
@jwt_required
def get_branches():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    branches = componyCode._get_branch(
        compony_code)
    if branches:
        return jsonify({"message": "success", "details": branches})
    return jsonify({"message": "Falid"})


@app.route("/get-agency")
@jwt_required
def get_agencys():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    agencys = componyCode._get_agents(
        compony_code)
    if agencys:
        return jsonify({"message": "success", "details": agencys})
    return jsonify({"message": "Falid"})


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
    agencys = componyCode._set_agents(
        compony_code, agency)
    if agencys:
        return jsonify({"message": "success"})
    return jsonify({"message": "Falid"})


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
                    return jsonify({"message": "Branch is requerd"}), 400
                break
        if not all([fullname, employeecode, compony_code]):
            return jsonify({"error": "Missing required fields"})
        validate = Validate(compony_code, employeecode)
        validate_user, user = validate.validate_employee()
        if validate_user:
            return jsonify({"message": "Faild"})
        status = attendance.update_face(
            employee_code=employeecode, branch=branch, add_img=file, company_code=compony_code, fullname=fullname, existing_office_kit_user=user)
        if status:
            return jsonify({"message": "success"})
        return jsonify({"message": "Faild"})

    return jsonify({"message": "file is missing"})


@app.route("/compare-face", methods=['POST'])
@jwt_required
def comare_face():
    user = request.user
    if 'file' not in request.files:
        return jsonify({"message": "File is missing"}), 400

    file = request.files['file']
    logger.info("Face comparison request received | user_id: %s | IP: %s | Timestamp: %s",
                user.get("employee_code"), request.remote_addr, now_ist_str())

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
        if not all([latitude, longitude]):
            logger.warning(
                "Location data missing for user_id: %s during face comparison", user.get("employee_code"))
            return jsonify({"message": "Missing data"}), 400
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            logger.info("Location received - Lat: %s, Lon: %s for user_id: %s",
                        str(latitude), str(longitude), user.get("employee_code"))
        except:
            return jsonify({"message": "Invalid location"}), 400
        logger.info("STARTING FACE COMPARISON | user_id: %s | company_code: %s | location_required: %s | time: %s",
                    user.get("employee_code"), user.get(
                        "compony_code"), str(location_settings),
                    now_ist_str())

        success, result = attendance.compare_faces(
            base_img=file,
            company_code=user.get("compony_code"),
            latitude=latitude,
            longitude=longitude,
            individual_login=individual_login,
            officekit_user=officekit_user
        )

        if success:
            logger.info("FACE COMPARISON SUCCESS | user_id: %s | result: %s | time: %s",
                        user.get("employee_code"), result, now_ist_str())
            return jsonify({"message": "success", "details": result}), 200
        else:
            logger.warning("FACE COMPARISON FAILED | user_id: %s | reason: %s | time: %s",
                           user.get("employee_code"), str(result), now_ist_str())
            return jsonify({"message": result}), 200
    else:
        logger.info("STARTING FACE COMPARISON | user_id: %s | company_code: %s | location_required: %s | time: %s",
                    user.get("employee_code"), user.get(
                        "compony_code"), str(location_settings),
                    now_ist_str())
        success, result = attendance.compare_faces(
            base_img=file,
            company_code=user.get("compony_code"),
            latitude=None,
            longitude=None,
            individual_login=individual_login,
            officekit_user=officekit_user
        )

        if success:
            logger.info("FACE COMPARISON SUCCESS | user_id: %s | result: %s | time: %s",
                        user.get("employee_code"), str(result), now_ist_str())
            return jsonify({"message": "success", "details": result}), 200
        else:
            logger.warning("FACE COMPARISON FAILED | user_id: %s | reason: %s | time: %s",
                           user.get("employee_code"), str(result), now_ist_str())
            return jsonify({"message": result}), 400


@app.route("/all-employees")
@jwt_required
def all_employees():
    user = request.user
    # data = request.get_json()
    # if not data:
    #     return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    data = userdetails.get_all_users(compony_code=compony_code)
    return jsonify({"message": "success", "data": data})


@app.route("/attandance-report", methods=['POST'])
@jwt_required
def attandance_report():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
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

    data = userdetails.get_attandance_report_all(
        compony_code=compony_code, starting_date=starting_date, ending_date=ending_date)
    return jsonify({"message": "success", "data": data})


@app.route("/edit-attandance", methods=['POST'])
@jwt_required
def edit_attandance():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get('compony_code')
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

    message = userdetails.edit_attandance_report(
        compony_code=compony_code, emploee_list_with_action=editable_details, editad_date=editad_date)
    if message:
        return jsonify({"message": message})
    return jsonify({"message": "Faild"})


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
            "employee_id": emp['employee_id'],
            "branch": emp["branch"],
            "action": emp['action'],
            "full_name": emp['full_name'] if emp['full_name'] else None,
            "file": request.files.get(f"file_{i}") if request.files.get(f"file_{i}") else None
        })
    if editable_details_files:
        message = userdetails.edit_user_details(
            compony_code, editable_details_files)
        return jsonify({"message": message})
    return jsonify({"message": "Faild"})


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


@app.route('/')
def home():
    return "Welcome to AttendEase API"


# def run_scheduler():
#     schedule.every(1).hours.do(job)
#     while True:
#         schedule.run_pending()
#         time.sleep(1)


# threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == "__main__":
    # cursor.execute("select * from ATTENDANCELOG_STAGING")
    # result = cursor.fetchone()
    # print(result, 'result = cursor.fetchone()result = cursor.fetchone()result = cursor.fetchone()')
    init_faiss_indexes()
    app.run(debug=True, port=5001, host="0.0.0.0")
