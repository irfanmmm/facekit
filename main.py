from flask import Flask, request, jsonify
from face_match.face_ml import FaceAttendance
from model.compony_model import ComponyModel
from helper.trigger_mail import send_mail_with_template
import requests as http
import sv_ttk
import tkinter
from tkinter import ttk

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
        
        status = attendance.update_face(employee_code=employeecode,add_img=file,company_code=compony_code,fullname=fullname)
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
        if not compony_code:
            return jsonify({"message": "compony_code is requerd"})
        match = attendance.compare_faces(file,compony_code)
        if match:
            return jsonify({"message": "success","details":match})
        return jsonify({"message": "Faild"})
    return jsonify({"message": "file is missing"})

@app.route("/logs", methods=['POST'])
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
    counts, data = attendance.get_logs(compony_code,from_date, to_date,page=page,limit=limit)
    return jsonify({"message": "success", "counts": counts, "data": data})

@app.route("/")

@app.route('/')
def home():
    return 'AttendEase APP API'

# import face_recognition
# import cv2
# import numpy as np

# # Load known faces and their encodings (from your training phase)
# known_face_encodings = []
# known_face_names = []

# # Example: Load a known face
# image_of_person1 = face_recognition.load_image_file("irfan.jpeg")
# person1_face_encoding = face_recognition.face_encodings(image_of_person1)[0]
# known_face_encodings.append(person1_face_encoding)
# known_face_names.append("Irfan")

# # Initialize webcam
# video_capture = cv2.VideoCapture(0)

# while True:
#     ret, frame = video_capture.read()
#     if not ret:
#         break

#     # Find all the faces and face encodings in the current frame
#     face_locations = face_recognition.face_locations(frame)
#     face_encodings = face_recognition.face_encodings(frame, face_locations)

#     for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
#         matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
#         name = "Unknown"

#         if True in matches:
#             first_match_index = matches.index(True)
#             name = known_face_names[first_match_index]

#         # Draw a box around the face and label it
#         cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
#         cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

#     cv2.imshow('Video', frame)

#     if cv2.waitKey(1) & 0xFF == ord('q'):
#         break

# video_capture.release()
# cv2.destroyAllWindows()

if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
