import logging
import os

log_path = r"C:\Users\ANT2\Documents\IMP\AttendEaseAPI\logs\face_comparison.log"

os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

print("Logging file created at:", log_path)
