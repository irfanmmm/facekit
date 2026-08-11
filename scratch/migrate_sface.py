import sys
import os
import cv2
import numpy as np
import glob
from dotenv import load_dotenv

sys.path.append("/home/ubuntu/facekit/facekit")
load_dotenv("/home/ubuntu/facekit/facekit/.env")

from model.database import get_database, _get_client

client = _get_client()

# Load Models
yunet_path = "/home/ubuntu/facekit/facekit/face_match/models/face_detection_yunet_2023mar.onnx"
sface_path = "/home/ubuntu/facekit/facekit/face_match/models/face_recognition_sface_2021dec.onnx"

detector = cv2.FaceDetectorYN.create(yunet_path, "", (300, 300), score_threshold=0.25, nms_threshold=0.3)
sface = cv2.FaceRecognizerSF.create(sface_path, "")

uploads_dir = "/home/ubuntu/facekit/facekit/face_match/uploads"

def generate_sface_encoding(image_path):
    image = cv2.imread(image_path)
    if image is None: return None
    
    h, w = image.shape[:2]
    max_dim = 600
    if h > max_dim or w > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = image.shape[:2]

    detector.setInputSize((w, h))
    _, faces = detector.detect(image)
    
    if faces is None or len(faces) == 0:
        return None
        
    face_box = faces[0]
    aligned_face = sface.alignCrop(image, face_box)
    feat = sface.feature(aligned_face)
    norm = np.linalg.norm(feat)
    if norm > 0:
        feat = feat / norm
    return [feat.flatten().tolist()]

def run_migration():
    dbs = client.list_database_names()
    for db_name in dbs:
        if db_name in ["admin", "local", "config"]: continue
        
        db = client[db_name]
        col_names = db.list_collection_names()
        
        for col_name in col_names:
            if col_name.startswith("encodings_"):
                company_code = col_name.split("encodings_")[1]
                collection = db[col_name]
                
                docs = collection.find({"is_delete": {"$ne": True}})
                for doc in docs:
                    emp_code = doc.get("employee_code")
                    if not emp_code: continue
                    
                    # Search for the user image in uploads
                    # Pattern: user_{employee_code}_..._{company_code}.jpg
                    search_pattern = os.path.join(uploads_dir, f"user_{emp_code}_*_{company_code}.jpg")
                    matches = glob.glob(search_pattern)
                    
                    if matches:
                        img_path = matches[0]
                        v2_encs = generate_sface_encoding(img_path)
                        
                        if v2_encs:
                            collection.update_one(
                                {"_id": doc["_id"]},
                                {"$set": {"encodings_v2": v2_encs}}
                            )
                            print(f"✅ Generated encodings_v2 for {emp_code} in {company_code}")
                        else:
                            print(f"❌ Failed to generate SFace encoding for {emp_code} (face not detected)")
                    else:
                        print(f"⚠️ No original image found for {emp_code} in {company_code}")

if __name__ == "__main__":
    print("Starting SFace Migration...")
    run_migration()
    print("Migration Complete.")
