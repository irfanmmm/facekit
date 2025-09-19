from flask import Flask, request, jsonify
from face_match.face_ml import FaceAttendance
from model.compony_model import ComponyModel
from helper.trigger_mail import send_mail_with_template
import requests as http

app = Flask(__name__)

OFFICE_KIT_API_KEY="wba1kit5p900egc12weblo2385"
OFFICE_KIT_PRIMERY_URL="http://appteam.officekithr.net/api/AjaxAPI/MobileUrl"

# ---------------- DB Connection ----------------

attendance = FaceAttendance()  # initialize once
componyCode = ComponyModel()  # initialize once


""" Register user """
@app.route('/signup', methods=['POST'])
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

    if not all([compony_name, _name, email, password, mobile_no, emp_count]):
        return jsonify({"error": "Missing required fields"})
    message,company_code = componyCode._set(compony_name,_name,email,password,mobile_no,emp_count)
    if message == "faild":
        return jsonify({"message": company_code})
    status = send_mail_with_template(email,email,password,company_code,'')
    if status: 
        return jsonify({"message": message})
    else:
        return jsonify({"message": "somthing went wrong"})


@app.route("/verify-compony-code",methods=['POST'])
def verify_compony_code():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    
    compony_code = data.get("code")
    if not compony_code:
        return jsonify({"message": "compony code is requerd"})
    
    # response = http.post(f"{OFFICE_KIT_PRIMERY_URL}?OfficeContent={{'ApiKey':'{OFFICE_KIT_API_KEY}','CompanyCode':'{compony_code}'}}")

    # if response['status'] == 'success':
    message = componyCode._verify(compony_code)
    if message == "success":
        return jsonify({"message": message})

    return jsonify({"message": message})

@app.route("/verify-admin",methods=['POST'])
def verify_admin():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No JSON body received"}), 400
    
    username = data.get("username")
    password = data.get("password")
    compony_code = data.get("compony_code")

    if not all([username,password]):
        return jsonify({"message": "Missing required fields"})
    
    message = componyCode._verify_admin(compony_code,username,password)
    return jsonify({"message": message})

@app.route("/add-employee-face",methods=['POST'])
def add_employee_face():
    if 'file' in request.files:
        data = request.form
        file = request.files.get('file')
        fullname = data.get('fullname')
        employeecode = data.get('employeecode')
        compony_code = data.get('compony_code')

        if not all([fullname, employeecode,compony_code]):
            return jsonify({"error": "Missing required fields"})
        
        status = attendance.update_face(employee_code=employeecode,add_img=file,compony_code=compony_code,fullname=fullname)
        if status:
            return jsonify({"message": "success"})
        return jsonify({"message": "Faild"})
    
    return jsonify({"message": "file is missing"})

@app.route("/compare-face",methods=['POST'])
def comare_face():
    if 'file' in request.files:
        file = request.files.get('file')
        data = request.form
        compony_code = data.get('compony_code')
        match = attendance.compare_faces(file,compony_code)
        if match:
            return jsonify({"message": "success","details":match})
        return jsonify({"message": "Faild"})
    return jsonify({"message": "file is missing"})












































# @app.route('/face_match', methods=['POST'])
# def face_match():
#     if 'file1' in request.files:
#         file1 = request.files.get('file1')
#         response = attendance.compare_faces(file1)
#         if response:
#             pass
#             # update_attendance(response, file1.filename)
#         return jsonify({"status": response})
#     return jsonify({"status": "No file provided"})






# @app.route('/add_face', methods=['POST'])
# def add_face():
#     if 'file1' in request.files:
#         file1 = request.files.get('file1')
#         img_name = file1.filename.split(".")[0]
#         response = attendance.update_face(img_name, file1)
#         return jsonify({"status": response})
#     return jsonify({"status": "No file provided"})

# # @app.route("/verify-compony-code",methods=['POST'])
# # def verify_code():
# #     data = request.get_json()
# #     if not data:
# #         return jsonify({"error": "No JSON body received"}), 400
    
# #     code = data.get("code")  # get value of 'code'

# #     officeContent = {
# #         "ApiKey": OFFICE_KIT_API_KEY,
# #         "CompanyCode": code,
# #     }

# #     response = http.post(f"http://appteam.officekithr.net/api/AjaxAPI/MobileUrl?OfficeContent={officeContent}")

# #     return jsonify(response.json())

# # @app.route("/verify-admin",methods=['POST'])
# # def verify_admin():
# #     data = request.get_json()
# #     if not data:
# #         return jsonify({"error": "No JSON body received"}), 400
    
# #     username = data.get("username") 
# #     password = data.get("password")

# #     # verify admin usign db
# #     return jsonify({"username":username, "password":password})

# @app.route("/add-employee",methods=['POST'])
# def add_employee():
#     data = request.get_json()
#     if not data:
#         return jsonify({"error": "No JSON body received"}), 400
    
#     fullname = data.get("fullname") 
#     employeecode = data.get("employeecode")

#     # verify admin usign db
#     return jsonify({"fullname":fullname, "employeecode":employeecode})

@app.route('/')
def home():
    return 'AttendEase APP API'

if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
