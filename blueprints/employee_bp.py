from flask import Blueprint, request, jsonify
from middleware.auth_middleware import jwt_required
from model.user_model import UserModel
from connection.all_emp import AllEmp
from connection.validate_officekit import Validate
from face_match.face_ml import FaceAttendance
from model.database import get_database
from utility.settings import Settings

employee_bp = Blueprint('employee', __name__)
attendance = FaceAttendance()

@employee_bp.route("/model-config", methods=['GET'])
def get_model_config():
    """Returns active model embedding dimensions (128d or 192d) and configuration"""
    return jsonify({
        "status": "success",
        "embedding_dim": 128,
        "model_name": "OpenCV_SFace",
        "threshold": 0.85,
        "onboarding_format": "base64",
        "scanning_format": "client_embedding"
    }), 200


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


    # Uses Settings.get_setting() (process-cached) instead of a fresh Settings()
    # instance — the instance path re-queries the settings collection from Mongo
    # on every single call since its cache never survives past one request.
    branch_requerd = Settings.get_setting(compony_code, "Branch Management")
    agency_requerd = Settings.get_setting(compony_code, "Agency Management")
    office_kit_user = Settings.get_setting(compony_code, "Office Kit Integration")
    employeecode_requerd = Settings.get_setting(compony_code, "Employee Code")
    shift_requerd = Settings.get_setting(compony_code, "Shift Management")

    branch = data.get('branch')
    agency = data.get('agency')
    employeecode = data.get('employeecode')
    shift = data.get('shift')


    # Base required fields - require images array or single base64 image
    required_fields = ["fullname", "gender"]
    if not data.get('images'):
        required_fields.append("base64")


    # Dynamic required fields based on settings
    if branch_requerd:
        required_fields.append("branch")
    if agency_requerd:
        required_fields.append("agency")
    if employeecode_requerd:
        required_fields.append("employeecode")
    if shift_requerd:
        required_fields.append("shift")

    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        return jsonify({"message": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    # validate = Validate(compony_code, employeecode,
    #                     isAdmin=user.get("is_admin", False))
    # validate_user, user_doc = validate.validate_employee()
    images = data.get("images")  # list[str] — base64 crops, one per pose
    if not images:
        single = data.get("base64")
        images = [single] if single else None

    client_embeddings = data.get("client_embeddings") or data.get("embeddings")

    status, message = attendance.update_face(
        branch=branch,
        agency=agency,
        add_images=images,
        company_code=compony_code,
        fullname=fullname,
        gender=gender,
        existing_office_kit_user=office_kit_user,
        employeecode=employeecode,
        client_embeddings=client_embeddings,
        shift=shift,
    )


    message = message if message else "something went wrong"
    if status:
        return jsonify({"status": True, "message": message}), 200
    return jsonify({"status": False, "message": message}), 200


@employee_bp.route("/compare-face", methods=['POST'])
@jwt_required
def comare_face():
    user = request.user
    data = request.get_json()

    if not data:
        return jsonify({
            "error": "JSON body error"
        }), 400

    # Cached (see add_employee_face for why) — this route runs on every
    # single attendance punch, so the saved Mongo round-trip matters most here.
    compony_code = user.get("compony_code")
    location_settings = Settings.get_setting(compony_code, "Location Tracking")
    individual_login = Settings.get_setting(compony_code, "Individual Login")
    officekit_user = Settings.get_setting(compony_code, "Office Kit Integration")

    latitude = 0
    longitude = 0
    if location_settings:
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not all([latitude, longitude]):
            return jsonify({"message": "Location is required"}), 200
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except:
            return jsonify({"message": "Invalid location"}), 200

    base64 = data.get("base64")
    embedding = data.get("client_embedding") or data.get("embedding")

    if not base64 and not embedding:
        return jsonify({"message": "Image or face embedding required"}), 200

    success, result = attendance.compare_faces(
        base_img=base64,
        company_code=compony_code,
        latitude=latitude,
        longitude=longitude,
        officekit_user=officekit_user,
        client_embedding=embedding,
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
    branch_id = user.get('branchId') if user.get('branchId') else data.get('branch')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    userdetails = AllEmp(compony_code)
    result = userdetails.get_all_emp(offset, limit, search, branch_id)
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


@employee_bp.route("/edit-employee-face", methods=['POST'])
@jwt_required
def edit_employee_face():
    user = request.user
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400

    employeecode = data.get("employeecode")
    base64 = data.get("base64")
    embedding = data.get("embedding")

    if not all([employeecode, base64]):
        return jsonify({"message": "employeecode and base64 are required"}), 400

    status, message = attendance.edit_employee_face(
        employee_code=employeecode,
        emp_face=base64,
        compony_code=compony_code,
        client_embedding=embedding
    )
    return jsonify({"message": message, "status": status})


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
