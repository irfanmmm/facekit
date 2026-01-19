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

import face_recognition as fs

import base64
import numpy as np
import cv2

IST = timezone(timedelta(hours=5, minutes=30))

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def now_ist_str():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"


app = Flask(__name__, template_folder='public/templates',
            static_folder='static', static_url_path='/static')
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

    content_type = request.headers.get("Content-Type", "").lower()
    if "multipart/form-data" in content_type:
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: <FORM-DATA SKIPPED>"
        )
        return

    raw_body = request.get_data(as_text=True)

    try:
        data = request.get_json(silent=True)

        if isinstance(data, dict) and "base64" in data:
            # Remove base64 only from log
            masked = data.copy()
            masked["base64"] = "<BASE64_CONTENT_REMOVED>"
            app.logger.info(
                f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {masked}"
            )
        else:
            # Log full JSON or raw body directly
            app.logger.info(
                f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {raw_body}"
            )

    except Exception:
        # If not JSON (form-data, text, file upload)
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {raw_body}"
        )


@app.after_request
def after_request(response):
    try:
        # Calculate duration
        start_time = g.start_time
        duration = time.time() - start_time
    except Exception:
        duration = 0
    try:
        response_data = response.get_data(as_text=True)
        ip = request.access_route[0] if request.access_route else request.remote_addr
        app.logger.info(
            f"REQUEST | {request.method} USER_IP | {ip} {request.path} | BODY: {response_data}")
    except Exception:
        response_data = "<unable to read response>"
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


@app.route("/get-branch",  methods=['POST'])
@jwt_required
def get_branches():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    offset = data.get("offset")
    limit = data.get("limit")
    search = data.get("search")

    componyCode = ComponyModel(compony_code)
    branches = componyCode._get_branch(
        compony_code, offset, limit, search)
    if branches:
        return jsonify({"message": "success", "details": branches})
    return jsonify({"message": "Failed"})


@app.route("/get-agency", methods=['POST'])
@jwt_required
def get_agencys():
    user = request.user
    compony_code = user.get('compony_code')
    data = request.get_json()
    branch_id = data.get('_id')

    if not data or not branch_id:
        return jsonify({"message": "No JSON body received"}), 400

    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    componyCode = ComponyModel(compony_code)
    agencys = componyCode._get_agents(
        compony_code, branch_id)
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
    data = request.get_json()
    base64 = data.get('base64')
    fullname = data.get('fullname')
    employeecode = data.get('employeecode')
    compony_code = user.get('compony_code')
    gender = data.get('gender')

    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    branch_requerd = False
    office_kit_user = False
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

        if settings.get("setting_name") == "Office Kit Integration" and settings.get("value"):
            office_kit_user = True

    if not all([fullname, employeecode, compony_code, base64, gender]):
        return jsonify({"error": "Missing required fields"})

    validate = Validate(compony_code, employeecode,
                        isAdmin=user.get("is_admin", False))
    validate_user, user = validate.validate_employee()
    if validate_user:
        return jsonify({"message": "User already exists in Face Database"})
    status, message = attendance.update_face(
        employee_code=employeecode, branch=branch, agency=agency, add_img=base64, company_code=compony_code, fullname=fullname, gender=gender, existing_office_kit_user=office_kit_user)
    message if message else "somthing went wrong"
    if status:
        return jsonify({"message": message})
    return jsonify({"message": message})


@app.route("/compare-face", methods=['POST'])
@jwt_required
def comare_face():
    user = request.user
    data = request.get_json()

    if not data:
        return jsonify({
            "error": "JSON body error"
        }), 400

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

    latitude = 0
    longitude = 0
    if location_settings:
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not all([latitude, longitude]):
            return jsonify({"message": "Missing data"}), 200
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except:
            return jsonify({"message": "Invalid location"}), 200

    base64 = data.get("base64")

    if not base64:
        return jsonify({"message": "Missing data"}), 200
    success, result = attendance.compare_faces(
        base_img=base64,
        company_code=user.get("compony_code"),
        latitude=latitude,
        longitude=longitude,
        officekit_user=officekit_user
    )

    if success:
        return jsonify({"message": "success", "details": result}), 200
    else:
        return jsonify({"message": result}), 200


@app.route("/compare-face-test", methods=['POST'])
def campare_face_test():
    import face_recognition as fs

    data = request.json
    base64_img = data.get("base64")
    boundary = data.get("boundry")

    if not base64_img or not boundary:
        return jsonify({"error": "base64 or boundary missing"}), 400

    # Strip header
    if "," in base64_img:
        base64_img = base64_img.split(",")[1]

    # Decode Base64
    try:
        img_bytes = base64.b64decode(base64_img)
    except:
        return jsonify({"error": "Invalid base64"}), 400

    # Convert to image
    np_arr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        return jsonify({"error": "Invalid image"}), 400

    # RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    # h, w, _ = image.shape

    # # Expand MLKit bounding box (30% recommended)
    # pad = int(min(boundary["width"], boundary["height"]) * 0.30)

    # top = max(0, boundary["top"] - pad)
    # left = max(0, boundary["left"] - pad)
    # bottom = min(h, boundary["top"] + boundary["height"] + pad)
    # right = min(w, boundary["left"] + boundary["width"] + pad)

    # fr_box = [(top, right, bottom, left)]

    fr_box = fs.face_locations(image_rgb)

    # Generate encoding
    encodings = fs.face_encodings(image_rgb, fr_box)
    if not encodings:
        return jsonify({"error": "Encoding failed"}), 400

    encoding = encodings[0]
    encoding = encoding / np.linalg.norm(encoding)    # normalize

    compony_code = "A337"
    db = get_database(compony_code)
    collection = db[f'encodings_{compony_code}']

    best_match = None
    best_distance = 999

    for user in collection.find({}, {"_id": 0}):
        enc = np.array(user["encodings"], dtype=float)
        enc = enc / np.linalg.norm(enc)   # normalize stored encoding

        # Calculate real face distance
        dist = np.linalg.norm(enc - encoding)

        if dist < best_distance:
            best_distance = dist
            best_match = user

    # Match threshold
    if best_distance <= 0.40:
        return jsonify({
            "message": "success",
            "details": {"fullname": best_match["fullname"]},
            "distance": best_distance
        })

    return jsonify({
        "message": "face not matching",
        "distance": best_distance,
        "message": "face not matching"
    })


@app.route("/update-face-test", methods=["POST"])
def update_face_test():
    data = request.json
    base64_img = data.get("base64")
    boundary = data.get("boundry")
    fullname = data.get("fullname")
    agency = data.get("agency")
    branch = data.get("branch")
    employeecode = data.get("employeecode")

    compony_code = "A337"
    db = get_database(compony_code)
    collection = db[f"encodings_{compony_code}"]

    # ---- VALIDATE INPUT ----
    if not base64_img or not boundary:
        return jsonify({"error": "base64 or boundary missing"}), 400

    # Remove possible header
    if "," in base64_img:
        base64_img = base64_img.split(",")[1]

    # Base64 → bytes
    try:
        img_bytes = base64.b64decode(base64_img)
    except:
        return jsonify({"error": "Invalid base64"}), 400

    # Bytes → numpy image
    np_arr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        return jsonify({"error": "Invalid image"}), 400

    # Convert BGR → RGB
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    fr_box = fs.face_locations(rgb)

    if len(fr_box) > 1:
        return jsonify({"message": "faild"})

    # ---- GET FACE ENCODING ----
    encodings = fs.face_encodings(rgb, fr_box)

    if not encodings:
        return jsonify({"error": "Face not detected properly"}), 400

    encoding = encodings[0].astype(float)

    # Normalize encoding → increases accuracy
    encoding = encoding / np.linalg.norm(encoding)

    # ---- CHECK IF EMPLOYEE ALREADY EXISTS ----
    existing = collection.find_one({"employee_code": employeecode})

    if existing:
        # Append encoding → multiple samples give better matching
        new_enc_list = existing.get("encodings", encoding.tolist())
        # new_enc_list.append(encoding.tolist())

        collection.update_one(
            {"employee_code": employeecode},
            {
                "$set": {
                    "fullname": fullname,
                    "branch": branch,
                    "agency": agency,
                    "encodings": new_enc_list,
                }
            }
        )
        return jsonify({"message": "Face updated successfully"})

    # ---- INSERT NEW EMPLOYEE ----
    data = {
        "company_code": compony_code,
        "employee_code": employeecode,
        "fullname": fullname,
        "branch": branch,
        "agency": agency,
        "encodings_list": encoding.tolist()  # store as list
    }

    collection.insert_one(data)

    return jsonify({"message": "success"})


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
    limit = data.get('limit')
    offset = data.get('offset')
    search = data.get('search') if data.get('search') else None
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
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    editable_details = data.get("editable_details")
    base64 = data.get("base64", None)

    allowed_fields = ["employee_code", "action",
                      "full_name", "branch", "agency"]

    action = editable_details.get("action")

    if action == 'E':
        for field in allowed_fields:
            if field not in editable_details or not editable_details[field]:
                return jsonify({"message": f"{field} is required"})
    elif action == 'D':
        if not editable_details.get("employee_code"):
            return jsonify({"message": "employee_code is required"})

    userdetails = UserModel(compony_code)
    message = userdetails.edit_user_details(
        compony_code, editable_details, base64=base64)
    return jsonify({"message": message})


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
    # from connection.officekit_onboarding import OnboardingOfficekit
    # OnboardingOfficekit()
    app.run(debug=True, port=5001, host="0.0.0.0")
