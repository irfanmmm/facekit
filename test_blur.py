import cv2
import numpy as np
import os

# Create a sharp image (random noise + edges)
sharp = np.zeros((100, 100), dtype=np.uint8)
cv2.rectangle(sharp, (20, 20), (80, 80), 255, -1)
cv2.circle(sharp, (50, 50), 10, 0, -1)

# Create a blurry image
blurry = cv2.GaussianBlur(sharp, (15, 15), 0)

# Simulate camera noise on blurry image
noise = np.random.normal(0, 10, blurry.shape).astype(np.uint8)
blurry_noisy = cv2.add(blurry, noise)

def test_laplacian(img, name):
    eq = cv2.equalizeHist(img)
    score_raw = cv2.Laplacian(img, cv2.CV_64F).var()
    score_eq = cv2.Laplacian(eq, cv2.CV_64F).var()
    print(f"{name} -> Raw: {score_raw:.2f} | Eq: {score_eq:.2f}")

test_laplacian(sharp, "Sharp")
test_laplacian(blurry, "Blurry (No Noise)")
test_laplacian(blurry_noisy, "Blurry (With Noise)")

