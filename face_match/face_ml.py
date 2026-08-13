import logging
import cv2
import os
import fcntl
import contextlib
import threading
import re

_global_thread_lock = threading.Lock()

@contextlib.contextmanager
def process_lock(lock_path):
    with _global_thread_lock:
        with open(lock_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

import numpy as np
try:
    import face_recognition as fr
except ImportError:
    fr = None
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
except ImportError:
    mp = None
    mp_python = None
    mp_vision = None
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from functools import lru_cache
from model.database import get_database
from connection.validate_officekit import Validate
from utility.settings import Settings
import uuid
from geopy.distance import geodesic
from .faiss_manager import FaceIndexManager
import time
import base64
from connection.officekit_punching import OfficeKitPunching
from connection.officekit_onboarding import OnboardingOfficekit
from model.compony_model import ComponyModel
WORKING_HOURES = 9
WORKING_SECONDS = 9 * 60 * 60
EXCEPTION_SECONDS = 300
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
uploads_path = os.path.join(BASE_DIR, "uploads")
os.makedirs(uploads_path, exist_ok=True)

log_path = "logs/compare(ml)facekit.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logger = logging.getLogger("face_ml")


def is_user_in_radius(branch_lat, branch_lng, user_lat, user_lng, radius_meters):
    branch = (branch_lat, branch_lng)
    user = (user_lat, user_lng)
    distance = geodesic(branch, user).meters
    return distance <= radius_meters, distance


def save_employee_image(image):
    filename = f"{uuid.uuid4().hex}.jpg"
    file_path = os.path.join(uploads_path, filename)
    logger.info(file_path)
    cv2.imwrite(file_path, image)
    return


def _quick_sanity_check(image_rgb: np.ndarray):
    """Cheap check for the client-embedding fast path — NOT a replacement
    for validate_face_image()'s full dlib-based checks, just enough to catch
    'no face was actually in this crop' (blank wall, hand over camera,
    heavily motion-blurred frame, extreme darkness) before it gets stored as
    someone's permanent face reference.
    """
    h, w = image_rgb.shape[:2]
    if h < 60 or w < 60:
        return False, "Image too small — please retake"

    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)

    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < 15:
        return False, f"Image too blurry (score: {blur_score:.1f}). Please retake."

    brightness = np.mean(gray)
    if brightness < 20:
        return False, "Image too dark. Please retake in better lighting."
    if brightness > 235:
        return False, "Image too bright/overexposed. Please retake."

    # Very low pixel variance usually means "flat surface, not a face"
    if np.std(gray) < 10:
        return False, "No clear face detected in image. Please retake."

    return True, "ok"


# Canonical 3D face landmark positions (rough, in mm, arbitrary but internally consistent scale).
# Order matches YuNet's 5-point landmark order: right eye, left eye, nose tip,
# right mouth corner, left mouth corner.
_MODEL_3D_POINTS = np.array([
    [-30.0, -30.0,  30.0],  # right eye
    [ 30.0, -30.0,  30.0],  # left eye
    [  0.0,   0.0,   0.0],  # nose tip
    [-25.0,  30.0,  20.0],  # right mouth corner
    [ 25.0,  30.0,  20.0],  # left mouth corner
], dtype=np.float64)


def _estimate_head_pose(landmarks_x, landmarks_y, w, h):
    """
    Real 3D head-pose estimation via solvePnP, using the 5 landmarks YuNet already
    provides. Returns (pitch, yaw, roll) in degrees, or None if solvePnP fails to converge.

    This replaces the old 2D eye/nose/mouth y-distance ratio, which is easily thrown off
    by facial-hair occlusion shifting the mouth landmark, and has no real concept of 3D
    geometry — it can pass extreme angles by coincidence.
    """
    try:
        image_points = np.array(list(zip(landmarks_x, landmarks_y)), dtype=np.float64)
        focal_length = w
        camera_matrix = np.array([
            [focal_length, 0, w / 2],
            [0, focal_length, h / 2],
            [0, 0, 1]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1))

        success = False
        rvec, tvec = None, None
        for flag in [getattr(cv2, 'SOLVEPNP_SQPNP', None), getattr(cv2, 'SOLVEPNP_EPNP', None), getattr(cv2, 'SOLVEPNP_ITERATIVE', None)]:
            if flag is None:
                continue
            try:
                success, rvec, tvec = cv2.solvePnP(
                    _MODEL_3D_POINTS, image_points, camera_matrix, dist_coeffs,
                    flags=flag
                )
                if success:
                    break
            except Exception:
                continue

        if not success or rvec is None:
            return None

        rmat, _ = cv2.Rodrigues(rvec)
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))
            yaw = np.degrees(np.arctan2(-rmat[2, 0], sy))
            roll = np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0]))
        else:
            pitch = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
            yaw = np.degrees(np.arctan2(-rmat[2, 0], sy))
            roll = 0.0

        return float(pitch), float(yaw), float(roll)
    except Exception as e:
        logger.warning(f"solvePnP head-pose estimation failed: {e}")
        return None


def _landmark_plausibility_check(landmarks_x, landmarks_y):
    """
    Sanity check independent of facial hair: interpupillary distance (eye_w) is a stable
    reference regardless of beard/occlusion. If dist_nose_mouth is wildly out of proportion
    to eye_w, the mouth landmark was probably placed unreliably (e.g. guessed through a
    beard) — flag it so a bad photo doesn't get a false "pass" from noisy landmarks.
    """
    eye_w = abs(landmarks_x[1] - landmarks_x[0])
    if eye_w <= 0:
        return True  # can't evaluate, don't block on this check alone

    mouth_y = (landmarks_y[3] + landmarks_y[4]) / 2
    nose_y = landmarks_y[2]
    dist_nose_mouth = abs(mouth_y - nose_y)

    ratio = dist_nose_mouth / eye_w
    # A plausible nose-to-mouth distance is roughly 0.3x-1.3x the interpupillary distance
    # for a face at a normal angle. Well outside that suggests unreliable landmarks.
    return 0.25 <= ratio <= 1.5


_SFACE_RECOGNIZER = None
_YUNET_DETECTOR = None



def _get_sface_recognizer():
    global _SFACE_RECOGNIZER
    if _SFACE_RECOGNIZER is None:
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "face_recognition_sface_2021dec.onnx")
        if os.path.exists(model_path):
            try:
                _SFACE_RECOGNIZER = cv2.FaceRecognizerSF.create(model_path, "")
                logger.info("Loaded SFace ONNX 128-d model successfully.")
            except Exception as e:
                logger.error(f"Failed to load SFace model: {e}")
    return _SFACE_RECOGNIZER


def _get_yunet_detector():
    global _YUNET_DETECTOR
    if _YUNET_DETECTOR is None:
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "face_detection_yunet_2023mar.onnx")
        if os.path.exists(model_path):
            try:
                _YUNET_DETECTOR = cv2.FaceDetectorYN.create(model_path, "", (300, 300), score_threshold=0.25, nms_threshold=0.3)
                logger.info("Loaded YuNet ONNX detector successfully with score_threshold=0.25.")
            except Exception as e:
                logger.error(f"Failed to load YuNet detector: {e}")
    return _YUNET_DETECTOR


_FACE_LANDMARKER = None


def _get_face_landmarker():
    """MediaPipe FaceLandmarker (478 points) — used for head-pose estimation
    only. YuNet's 5-point landmarks + solvePnP proved unreliable for extreme
    camera angles (e.g. phone held low, pointed steeply up at the chin): two
    real photos of the same near-identical bad pose measured 22 degrees apart,
    one of them landing inside the "acceptable" threshold. FaceLandmarker's
    built-in facial transformation matrix, backed by many more constraint
    points, reads the same two photos as -37 and -42 degrees pitch —
    consistent with each other and clearly over any reasonable limit.
    """
    global _FACE_LANDMARKER
    if _FACE_LANDMARKER is None and mp_vision is not None:
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "face_landmarker.task")
        if os.path.exists(model_path):
            try:
                base_options = mp_python.BaseOptions(model_asset_path=model_path)
                options = mp_vision.FaceLandmarkerOptions(
                    base_options=base_options,
                    output_face_blendshapes=False,
                    output_facial_transformation_matrixes=True,
                    num_faces=1,
                )
                _FACE_LANDMARKER = mp_vision.FaceLandmarker.create_from_options(options)
                logger.info("Loaded MediaPipe FaceLandmarker (478-point) model successfully.")
            except Exception as e:
                logger.error(f"Failed to load MediaPipe FaceLandmarker: {e}")
    return _FACE_LANDMARKER


def _estimate_head_pose_mediapipe(image_rgb):
    """Robust pitch/yaw/roll via MediaPipe FaceLandmarker's facial transformation
    matrix. Returns (pitch, yaw, roll) in degrees, or None if unavailable/no face.
    """
    landmarker = _get_face_landmarker()
    if landmarker is None:
        return None
    try:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        result = landmarker.detect(mp_image)
        if not result.facial_transformation_matrixes:
            return None
        rmat = np.array(result.facial_transformation_matrixes[0])[:3, :3]
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        singular = sy < 1e-6
        if not singular:
            pitch = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))
            yaw = np.degrees(np.arctan2(-rmat[2, 0], sy))
            roll = np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0]))
        else:
            pitch = np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1]))
            yaw = np.degrees(np.arctan2(-rmat[2, 0], sy))
            roll = 0.0
        return float(pitch), float(yaw), float(roll)
    except Exception as e:
        logger.warning(f"MediaPipe head-pose estimation failed: {e}")
        return None


def validate_face_image(image, enable_rotation=False):
    """
    Validates face quality and extracts 128-d SFace embedding vector.
    Expects BGR image format from OpenCV imdecode/imread.
    """
    h, w = image.shape[:2]
    if h < 64 or w < 64:
        return False, "Image resolution too low. Minimum required is 64x64.", None


    max_dim = 600
    if h > max_dim or w > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = image.shape[:2]

    detector = _get_yunet_detector()
    sface = _get_sface_recognizer()

    if detector is not None and sface is not None:
        detector.setInputSize((w, h))
        _, faces = detector.detect(image)

        # Check if we need rotation fallback (no faces or low confidence)
        needs_rotation = True
        if faces is not None and len(faces) > 0:
            max_conf = max([float(f[14]) if len(f) > 14 else 1.0 for f in faces])
            if max_conf >= 0.20:
                needs_rotation = False

        if needs_rotation and enable_rotation:
            # Auto-rotate fallback for mobile images sent sideways (90° CW, 90° CCW, 180°)
            best_rot_faces = None
            best_rot_img = None
            best_conf = 0.0

            for rot_flag in [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180]:
                rot_img = cv2.rotate(image, rot_flag)
                rh, rw = rot_img.shape[:2]
                detector.setInputSize((rw, rh))
                _, rfaces = detector.detect(rot_img)
                if rfaces is not None and len(rfaces) > 0:
                    r_conf = max([float(f[14]) if len(f) > 14 else 1.0 for f in rfaces])
                    if r_conf > best_conf:
                        best_conf = r_conf
                        best_rot_faces = rfaces
                        best_rot_img = rot_img
                        h, w = rh, rw
            
            if best_rot_faces is not None and best_conf >= 0.20:
                logger.info(f"🔄 Auto-rotated image for better face detection (conf: {best_conf:.2f}).")
                image = best_rot_img
                faces = best_rot_faces

        if faces is None or len(faces) == 0:
            return False, "No clear face detected. Please hold steady facing the camera.", None

        if len(faces) > 1:
            return False, "Multiple faces detected.", None

        face_box = faces[0]
        confidence = float(face_box[14]) if len(face_box) > 14 else 1.0

        if confidence < 0.20:
            return False, f"Face feature confidence low ({confidence:.2f}). Please hold steady facing camera.", None

        # Check if all 5 facial landmarks are within the frame bounds and face angle is straight
        if len(face_box) >= 14:
            landmarks_x = face_box[4:14:2]
            landmarks_y = face_box[5:14:2]
            landmark_margin = 5
            for lx, ly in zip(landmarks_x, landmarks_y):
                if lx < landmark_margin or lx > w - landmark_margin or ly < landmark_margin or ly > h - landmark_margin:
                    return False, "Facial features (eyes/mouth) are partially outside the frame. Please center your face.", None

            # Nose Centering Check (Prevents half-cut-off faces)
            nose_x_ratio = landmarks_x[2] / w
            nose_y_ratio = landmarks_y[2] / h
            if nose_x_ratio < 0.25 or nose_x_ratio > 0.75 or nose_y_ratio < 0.25 or nose_y_ratio > 0.75:
                return False, "Face is off-center or partially outside the frame. Please center your face.", None

            # Pitch/Yaw/Roll Check. Primary source is MediaPipe FaceLandmarker's
            # 478-point facial transformation matrix — far more robust than a
            # 5-point solvePnP fit for extreme angles (verified: two real photos
            # of the same "camera held low, pointed up" bad pose measured 22
            # degrees apart under the old 5-point approach, one landing inside
            # the acceptable range; FaceLandmarker reads both consistently at
            # -37/-42 degrees). Falls back to the 5-point solvePnP estimate only
            # if the FaceLandmarker model/dependency isn't available.

            # First: sanity-check the landmarks themselves before trusting pose math built on them.
            if not _landmark_plausibility_check(landmarks_x, landmarks_y):
                return False, "Could not reliably read facial features. Please ensure your face is unobstructed and try again.", None

            image_rgb_for_pose = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pose = _estimate_head_pose_mediapipe(image_rgb_for_pose)
            if pose is None:
                pose = _estimate_head_pose(landmarks_x, landmarks_y, w, h)
            if pose is not None:
                pitch, yaw_deg, roll_deg = pose

                MAX_PITCH_DEG = 15.0  # up/down tilt — tune after testing real bad-angle samples
                MAX_YAW_DEG = 20.0    # left/right turn
                MAX_ROLL_DEG = 15.0   # sideways head tilt

                if abs(pitch) > MAX_PITCH_DEG:
                    direction = "up" if pitch > 0 else "down"
                    return False, f"Head is tilted too far {direction}. Please hold the phone at eye level and look straight at the camera.", None

                if abs(yaw_deg) > MAX_YAW_DEG:
                    return False, "Face is turned to the side. Please look straight at the camera.", None

                if abs(roll_deg) > MAX_ROLL_DEG:
                    return False, "Head is tilted sideways. Please keep your head straight.", None
            else:
                # Neither MediaPipe nor the solvePnP fallback could produce a pose
                # (model unavailable, or landmarks too degenerate to trust).
                # Fail closed rather than silently skipping the pose check.
                return False, "Could not determine face angle. Please hold steady facing the camera.", None
        bbox = face_box[:4].astype(int)
        face_x, face_y, face_w, face_h = max(0, bbox[0]), max(0, bbox[1]), bbox[2], bbox[3]

        # Bounding box check — YuNet naturally pads bbox a few px beyond image edges,
        # so allow a small fixed tolerance (10px) to avoid false positives on valid faces.
        bbox_tol = 10
        if (bbox[0] < -bbox_tol or
            bbox[1] < -bbox_tol or
            bbox[0] + bbox[2] > w + bbox_tol or
            bbox[1] + bbox[3] > h + bbox_tol):
            return False, "Face is too close to the edge of the frame. Please center your face.", None

        # Face area coverage check. This validator sees two very different shapes
        # of input: a full, uncropped photo (registration) where the face is a
        # small fraction of the frame, and an already tightly pre-cropped square
        # (attendance punch) where the face fills nearly all of it — so the floor
        # has to be low enough to admit both, not tuned to either one specifically.
        if (face_w * face_h) < (0.04 * w * h) or face_w < 40 or face_h < 40:
            return False, "Face too small in frame. Please move closer.", None

        # Extreme close-ups where the face outline is actually clipped are caught
        # by the bbox_tol check above (the face box exceeding the frame bounds).
        # A tighter percentage-based margin was tried here and removed: it can't
        # distinguish a genuinely clipped registration photo from the punch
        # flow's already tight, ~5%-padded pre-cropped image — both land in the
        # same few-percent range, so it risked rejecting legitimate punch attempts.

        # Quality check on raw un-interpolated face crop (Tenengrad Sobel Gradient Focus Metric)
        crop_raw = image[face_y:face_y + face_h, face_x:face_x + face_w]
        if crop_raw.size > 0:
            gray_crop = cv2.cvtColor(crop_raw, cv2.COLOR_BGR2GRAY)
            gx = cv2.Sobel(gray_crop, cv2.CV_64F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray_crop, cv2.CV_64F, 0, 1, ksize=3)
            tenengrad_score = float(np.mean(gx**2 + gy**2))

            if tenengrad_score < 120:
                return False, f"Face image is blurry (focus score: {tenengrad_score:.0f}). Please hold steady and wipe lens.", None

        # Quality check on aligned face
        aligned_face = sface.alignCrop(image, face_box)
        gray = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2GRAY)
        
        brightness = float(np.mean(gray))
        if brightness < 15:
            return False, f"Face is too dark (score: {brightness:.2f}). Increase lighting.", None
        if brightness > 245:
            return False, f"Face is too bright (score: {brightness:.2f}). Reduce lighting.", None

        # Facial feature texture check — reject false positive non-face images (ears, skin patches, clothing)
        left_eye_crop = gray[35:55, 25:48]
        right_eye_crop = gray[35:55, 64:87]
        avg_eye_std = float(np.std(left_eye_crop) + np.std(right_eye_crop)) / 2.0
        if avg_eye_std < 5.0:
            return False, "No clear facial features (eyes) detected. Please face the camera.", None

        feat = sface.feature(aligned_face)
        norm = np.linalg.norm(feat)
        if norm > 0:
            feat = feat / norm
        encodings = [feat.flatten()]

        # Generate fake face_locations tuple for caller compatibility
        top, left = max(0, bbox[1]), max(0, bbox[0])
        bottom, right = min(h, top + face_h), min(w, left + face_w)
        face_locations = [(top, right, bottom, left)]

        return True, face_locations, encodings

    elif fr is not None:
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        face_locations = fr.face_locations(image_rgb)
        if not face_locations:
            return False, "No face detected.", None
        if len(face_locations) > 1:
            return False, "Multiple faces detected.", None

        encodings = fr.face_encodings(image_rgb, face_locations, num_jitters=1)
        if not encodings:
            return False, "Face encoding failed.", None

        return True, face_locations, encodings
    else:
        return False, "No face recognition model available.", None


@lru_cache(maxsize=128)
def _get_local_branch_cached(company_code, branch_name):
    db = get_database(company_code)
    return db[f'branch_{company_code}'].find_one({
        "compony_code": company_code,
        "branch_name": branch_name
    })


class FaceAttendance:
    def __init__(self):
        pass

    def compare_faces(self, base_img=None, company_code=None, latitude=0, longitude=0, officekit_user=False, client_embedding=None):
        try:
            current_encoding = None

            # 1. Primary: Server-side OpenCV SFace 128-d model with 5-point landmark affine alignment
            if base_img:
                try:
                    img_bytes = base64.b64decode(base_img)
                    np_arr = np.frombuffer(img_bytes, np.uint8)
                    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                except Exception:
                    image = None

                if image is not None:
                    # DEBUG: Uncomment lines below to save debug scan images to disk if needed
                    # try:
                    #     debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'scanned_faces')
                    #     os.makedirs(debug_dir, exist_ok=True)
                    #     ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    #     save_path = os.path.join(debug_dir, f"scan_{ts}.jpg")
                    #     cv2.imwrite(save_path, image)
                    #     file_size_kb = os.path.getsize(save_path) / 1024.0
                    #     logger.info(f"📸 Saved debug scan image: {save_path} ({file_size_kb:.2f} KB)")
                    # except Exception as save_err:
                    #     print(f"Debug save error: {save_err}")

                    ok, message, encodings = validate_face_image(image)
                    if ok and encodings:
                        current_encoding = encodings[0]
                    else:
                        return False, message



            # 2. Fallback: Client embedding payload if base_img is omitted
            if current_encoding is None and client_embedding is not None and isinstance(client_embedding, list):
                if len(client_embedding) >= 128:
                    arr = np.array(client_embedding[:128], dtype=np.float32)
                    n = np.linalg.norm(arr)
                    if n > 0:
                        current_encoding = arr / n

            if current_encoding is None:
                return False, "Could not detect or extract face from camera image"

            # OpenCV SFace L2 Distance Match Threshold (Stricter for 1-to-N identification)
            MAX_ALLOWED_DISTANCE = 0.85
            manager = FaceIndexManager(company_code)
            candidates = manager.search(
                current_encoding, k=10, threshold=MAX_ALLOWED_DISTANCE
            )
            
            if not candidates:
                return False, "No matching face found"

            # Get best match
            best = min(candidates, key=lambda x: x["distance"])

            if best["distance"] > MAX_ALLOWED_DISTANCE:
                return False, f"Face not recognized (distance: {best['distance']:.3f})"

            employee = best["employee"]

            # Geo-fencing check
            branch_name = employee.get("branch")
            db = get_database(company_code)

            if Settings.get_setting(company_code, "Location Tracking"):
                if branch_name:
                    if officekit_user:
                        off = OfficeKitPunching(company_code)
                        branch = off.retreve_codinates(branch_name)
                    else:
                        branch = _get_local_branch_cached(
                            company_code, branch_name)
                    if branch and all(k in branch for k in ("latitude", "longitude", "radius")):
                        in_radius, dist = is_user_in_radius(
                            branch["latitude"], branch["longitude"], latitude, longitude, branch["radius"])
                        if not in_radius:
                            return False, f"Outside allowed area ({dist:.1f}m away)"

            # Log Attendance
            return self._log_attendance(company_code, employee, best["distance"], db, officekit_user)

        except Exception as e:
            print(f"[FaceAttendance] Error: {e}")
            logger.info(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False, "System error"

    def update_face(self, branch, agency, add_images=None, company_code=None, fullname=None, gender=None, existing_office_kit_user=False, employeecode=None, add_img=None, client_embeddings=None, client_embedding=None):
        try:
            current_encodings = []
            primary_image = None

            # 1. Primary: Process Base64 images through server-side OpenCV SFace 128-d model
            images_input = add_images
            if not images_input and add_img:
                images_input = [add_img]

            if images_input and isinstance(images_input, list):
                for idx, img_b64 in enumerate(images_input):
                    if not img_b64:
                        continue
                    try:
                        img_bytes = base64.b64decode(img_b64)
                        np_arr = np.frombuffer(img_bytes, np.uint8)
                        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                        # Debug: Save image to test it
                        # if image is not None:
                        #     import time
                        #     import os
                        #     debug_dir = os.path.join(os.path.dirname(BASE_DIR), "scratch")
                        #     os.makedirs(debug_dir, exist_ok=True)
                        #     debug_path = os.path.join(debug_dir, f"test_add_face_{int(time.time())}_{idx}.jpg")
                        #     cv2.imwrite(debug_path, image)
                        #     logger.info(f"Saved debug image to {debug_path}")

                    except Exception as e:
                        logger.error(f"Error decoding image: {e}")
                        image = None

                    if image is None:
                        return False, f"Pose {idx + 1}: Invalid image data"

                    ok, message, encodings = validate_face_image(image, enable_rotation=True)
                    if not ok or not encodings:
                        return False, f"Pose {idx + 1}: {message}"

                    enc_list = encodings[0].tolist() if hasattr(encodings[0], "tolist") else list(encodings[0])
                    current_encodings.append(enc_list)
                    if primary_image is None:
                        primary_image = image

            # 2. Fallback: On-device client_embeddings vector payloads
            if not current_encodings:
                if client_embeddings and isinstance(client_embeddings, list):
                    for emb in client_embeddings:
                        if isinstance(emb, list) and len(emb) == 128:
                            arr = np.array(emb, dtype=np.float32)
                            n = np.linalg.norm(arr)
                            if n > 0:
                                current_encodings.append((arr / n).tolist())



            if not current_encodings:
                return False, "No valid face encodings generated"




            with process_lock(f"/tmp/facekit_add_face_{company_code}.lock"):
                db = get_database(company_code)
                collection = db[f"encodings_{company_code}"]

                # Allow duplicate names for new employees (employee_code is the unique identifier)
                # if fullname and str(fullname).strip():
                #     clean_fullname = str(fullname).strip()
                #     existing_by_name = collection.find_one({
                #         "fullname": {"$regex": f"^{re.escape(clean_fullname)}$", "$options": "i"},
                #         "is_delete": {"$ne": True}
                #     })
                #     if existing_by_name:
                #         existing_code = existing_by_name.get('employee_code')
                #         if employeecode and existing_code == employeecode:
                #             # It's the same employee being updated, so don't block
                #             pass
                #         else:
                #             msg = f"An employee with the name '{clean_fullname}' is already registered ({existing_code})."
                #             logger.info(msg)
                #             return False, msg

                # Generate / validate employee code
                compony = ComponyModel(compony_code=company_code)
                if not employeecode:
                    employee_code = compony._generate_employee_code(company_code)
                else:
                    employee_code = employeecode.strip() if employeecode else employeecode
                    if compony._check_employee_code(company_code, employee_code):
                        return False, "This employee already exists"

                # Save primary photo to disk
                if primary_image is not None:
                    filename = f"user_{employee_code}_{branch}_{agency}_{fullname}_{company_code}.jpg"
                    filepath = os.path.join(uploads_path, filename)
                    cv2.imwrite(filepath, primary_image)

                # Duplicate check against every pose (SFace 128-d space)
                # Adjusted threshold to 1.05 to balance catching true duplicates without false positives
                DUPLICATE_CHECK_THRESHOLD = 1.05
                cashe = FaceIndexManager(company_code)



                for pose_vec in current_encodings:
                    search_enc = np.array(pose_vec, dtype=np.float32)
                    candidates = cashe.search(search_enc, k=10, threshold=DUPLICATE_CHECK_THRESHOLD)
                    for cand in candidates:
                        matched_emp_code = cand["employee"].get("employee_code", "")
                        if matched_emp_code and matched_emp_code == employee_code:
                            continue

                        matched_emp = cand["employee"].get("fullname", "Unknown")
                        matched_dist = cand["distance"]
                        msg = f"This face is already registered to employee '{matched_emp}' ({matched_emp_code})."
                        print(f"⚠️ Duplicate face registration blocked! {msg} (Distance: {matched_dist:.3f})")
                        logger.info(f"Duplicate face registration blocked! {msg} (Distance: {matched_dist:.3f})")
                        return False, msg


                # Store all pose encodings in MongoDB
                data = {
                    "company_code": company_code,
                    "employee_code": employee_code,
                    "branch": branch,
                    "agency": agency,
                    "fullname": fullname,
                    "existing_user_officekit": existing_office_kit_user,
                    "encodings": current_encodings,
                    "encodings_v2": current_encodings,  # SFace 128-d vectors
                    "created_date": datetime.now()
                }

                db = get_database(company_code)
                collection = db[f"encodings_{company_code}"]
                result = collection.insert_one(data)

                cashe.add_employee({
                    "_id": result.inserted_id,
                    "encodings_v2": current_encodings,
                    "company_code": company_code,
                    "employee_code": employee_code,
                    "branch": branch,
                    "agency": agency,
                    "fullname": fullname,
                    "existing_user_officekit": existing_office_kit_user
                })

            if Settings.get_setting(company_code, "Office Kit Onboarding"):
                import threading
                def _bg_onboard():
                    try:
                        add_user = OnboardingOfficekit(company_code)
                        add_user.add_user(employee_code, branch, agency, company_code, fullname, gender)
                    except Exception as ex:
                        logger.error(f"OfficeKit Onboarding error: {ex}")
                threading.Thread(target=_bg_onboard).start()

            return True, "success"

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in update_face: {e}")
            logger.info(f"ERROR: {e}")
            return False, "System error during face update"


    def add_employee_pose(self, employee_code, company_code, add_img):
        """Append an additional pose to an existing employee using server-side dlib."""
        try:
            if not add_img:
                return False, "Image required"
            img_bytes = base64.b64decode(add_img)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if image is None:
                return False, "Invalid image format"

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            ok, message, encodings = validate_face_image(image_rgb, enable_rotation=True)
            if not ok or not encodings:
                return False, message if message else "Face not detected"

            new_vec = encodings[0].tolist()

            db = get_database(company_code)
            collection = db[f"encodings_{company_code}"]

            doc = collection.find_one({"employee_code": employee_code, "company_code": company_code})
            if not doc:
                return False, "Employee not found"

            existing = doc.get("encodings", [])
            if existing and not isinstance(existing[0], list):
                existing = [existing]

            if len(existing) >= 4:
                return False, "Maximum poses already stored for this employee"

            collection.update_one(
                {"employee_code": employee_code, "company_code": company_code},
                {"$push": {"encodings": new_vec}}
            )

            FaceIndexManager(company_code).rebuild_index()
            return True, "Pose added successfully"

        except Exception as e:
            logger.error(f"add_employee_pose error: {e}")
            return False, "System error adding pose"

    def edit_employee_face(self, employee_code, emp_face, compony_code, existing_officekit_user=None, client_embedding=None):
        employee_code = employee_code.strip() if employee_code else employee_code
        try:
            if not emp_face:
                return False, "Image required"

            try:
                img_bytes = base64.b64decode(emp_face)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            except Exception:
                return False, "Invalid image data"

            if image is None:
                return False, "Invalid image format"

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            ok, message, encodings = validate_face_image(image_rgb, enable_rotation=True)
            if not ok or not encodings:
                return False, message if message else "Could not detect face"

            current_encoding = [encodings[0].tolist()]

            db = get_database(compony_code)
            enc_collection = db[f"encodings_{compony_code}"]

            enc_collection.update_one(
                {"employee_code": employee_code, "company_code": compony_code},
                {"$set": {"encodings": current_encoding}},
            )

            cache = FaceIndexManager(compony_code)
            cache.rebuild_index()
            return True, "Face updated successfully"

        except Exception as e:
            print(f"Error in edit_employee_face: {e}")
            return False, "System error during face edit"

            print(f"Error in edit_user_details: {e}")
            logger.info(f"ERROR: {e}")
            return False, "System error while updating user"

    def _log_attendance(self, company_code: str, employee: dict, distance: float, db, officekit_user=False, async_officekit=False):
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        collection_name = f"attandance_{company_code}_{now.strftime('%Y-%m')}"
        collection = db[collection_name]

        filter_query = {
            "employee_id": employee["employee_code"],
            "date": {"$gte": today_start, "$lt": tomorrow_start}
        }
        record = collection.find_one(filter_query)

        direction = "in"
        log_entry = {
            "direction": "in",
            "time": now,
            "confidence_distance": round(distance, 4)
        }

        if record and record.get("log_details"):
            last_log = record["log_details"][-1]
            if last_log.get("direction") == "in":
                direction = "out"
                duration = (now - last_log["time"]).total_seconds()
                log_entry["direction"] = "out"

                present = ""
                including_exception = max(duration - EXCEPTION_SECONDS, 0)
                if including_exception >= WORKING_SECONDS:
                    present = "P"
                collection.update_one(
                    filter_query,
                    {
                        "$set": {"present": present},
                        "$push": {"log_details": log_entry},
                        "$inc": {"total_working_time": duration}
                    }
                )
            else:
                collection.update_one(
                    filter_query,
                    {"$push": {"log_details": log_entry}}
                )
        elif record:
            # First check-in of the day
            _filter = {
                "employee_id": employee["employee_code"],
            }

            _updated_data = {
                "company_code": company_code,
                "fullname": employee["fullname"],
                "date": now,
                "present": "",
                "total_working_time": 0,
                "updated_at": datetime.utcnow()
            }

            collection.update_one(
                _filter,
                {
                    "$set": _updated_data,
                    "$push": {
                        "log_details": log_entry
                    }
                },
                upsert=True
            )
        else:
            collection.insert_one({
                "employee_id": employee["employee_code"],
                "fullname": employee["fullname"],
                "company_code": company_code,
                "date": now,
                "total_working_time": 0,
                "present": "",
                "log_details": [log_entry]
            })

        if officekit_user:
            try:
                working_hours = OfficeKitPunching(company_code)
                duration_str = working_hours.retreve_working_hours(employee["employee_code"])
            except Exception as e:
                logger.error(f"Failed to retrieve working hours from OfficeKit: {e}")
                duration_str = "00:00:00"
        else:
            total_time_seconds = 0
            if record:
                total_time_seconds = record.get("total_working_time", 0)
            
            if direction == "out":
                total_time_seconds += duration

            hours, remainder = divmod(total_time_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

        if officekit_user:
            import threading
            def _bg_punch(dir_val, emp_code, comp_code):
                try:
                    punching = OfficeKitPunching(comp_code)
                    punching.punchin_punchout(dir_val, emp_code)
                except Exception as e:
                    logger.error(f"Background Punching Error: {e}")

            t = threading.Thread(target=_bg_punch, args=(direction, employee["employee_code"], company_code), daemon=True)
            t.start()


        return True, {
            "fullname": employee["fullname"],
            "employee_code": employee["employee_code"],
            "direction": direction,
            "working_time": duration_str,
            "confidence_distance": round(distance, 4),
            "message": "Attendance marked successfully"
        }


# Pre-load SFace and YuNet ONNX AI models into RAM at server startup
try:
    _get_sface_recognizer()
    _get_yunet_detector()
except Exception as e:
    logger.warning(f"Backend AI model pre-warmup warning: {e}")

