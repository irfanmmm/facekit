import cv2
import time
import numpy as np
import face_recognition as fr

# Create a dummy image 800x800
img = np.random.randint(0, 255, (800, 800, 3), dtype=np.uint8)

start = time.time()
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
gray_eq = cv2.equalizeHist(gray)
blur_score = cv2.Laplacian(gray_eq, cv2.CV_64F).var()
print(f"Blur detection: {time.time() - start:.3f}s")

start = time.time()
locs = fr.face_locations(img)
print(f"Face locations: {time.time() - start:.3f}s")

# Add a dummy face box to test encoding
start = time.time()
enc = fr.face_encodings(img, [(100, 200, 200, 100)])
print(f"Face encodings: {time.time() - start:.3f}s")
