from flask import Blueprint, request, jsonify
from middleware.auth_middleware import jwt_required
from model.user_model import UserModel
from connection.validate_officekit import Validate
from face_match.face_ml import FaceAttendance

employee_bp = Blueprint('employee', __name__)
attendance = FaceAttendance()

@employee_bp.route("/add-employee-face", methods=['POST'])
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
    validate_user, user_doc = validate.validate_employee()
    if validate_user:
        return jsonify({"message": "User already exists in Face Database"})
    status, message = attendance.update_face(
        employee_code=employeecode, branch=branch, agency=agency, add_img=base64, company_code=compony_code, fullname=fullname, gender=gender, existing_office_kit_user=office_kit_user)
    message = message if message else "somthing went wrong"
    if status:
        return jsonify({"message": message})
    return jsonify({"message": message})


@employee_bp.route("/compare-face", methods=['POST'])
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
        officekit_user=True
    )

    if success:
        return jsonify({"message": "success", "details": result}), 200
    else:
        return jsonify({"message": result}), 200


@employee_bp.route("/all-employees", methods=['POST'])
@jwt_required
def all_employees():
    user = request.user
    data = request.get_json()
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
    result = userdetails.get_all_users(
        compony_code=compony_code, limit=limit, offset=offset, search=search)
    return jsonify({"message": "success", "data": result})


@employee_bp.route("/edit-user", methods=['POST'])
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


@employee_bp.route("/remove-deuplicate-encodings", methods=['POST'])
def remove_duplicate_encodings():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = data.get("compony_code")
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})
    userdetails = UserModel(compony_code)
    message = userdetails.find_duplicate_faces(compony_code)
    return jsonify({"message": message})
