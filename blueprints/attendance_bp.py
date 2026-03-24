from flask import Blueprint, request, jsonify
from middleware.auth_middleware import jwt_required
from model.user_model import UserModel
from face_match.face_ml import FaceAttendance

attendance_bp = Blueprint('attendance_reports', __name__)
attendance = FaceAttendance()

@attendance_bp.route("/attandance-report", methods=['POST'])
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
    result = userdetails.get_attandance_report(
        compony_code=compony_code, employee_code=employee_code, starting_date=starting_date, ending_date=ending_date)
    return jsonify({"message": "success", "data": result})


@attendance_bp.route("/attandance-report-all", methods=['POST'])
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
    result = userdetails.get_attandance_report_all(
        compony_code=compony_code, starting_date=starting_date, ending_date=ending_date, limit=limit, offset=offset, search=search)
    return jsonify({"message": "success", "data": result})


@attendance_bp.route("/edit-attandance", methods=['POST'])
@jwt_required
def edit_attandance():
    user = request.user
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    compony_code = user.get('compony_code')
    if not compony_code:
        return jsonify({"message": "compony_code is requerd"})

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


@attendance_bp.route("/logs", methods=['POST'])
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
    counts, result = attendance.get_logs(
        compony_code, from_date, to_date, page=page, limit=limit)
    return jsonify({"message": "success", "counts": counts, "data": result})
