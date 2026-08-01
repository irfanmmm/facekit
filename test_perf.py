import os, time

start = time.time()
files = os.listdir("face_match/uploads")
print(f"listdir took: {time.time() - start:.4f}s for {len(files)} files")

emp_codes = ["emp-1748", "34739", "emp-6415", "emp-9626", "emp-8973", "fake-1", "fake-2", "fake-3"] * 6
emp_codes = emp_codes[:50]
start = time.time()

image_map = {}
for filename in files:
    full = filename.lower()
    for code in emp_codes:
        if code in full:
            image_map[code] = filename
            break
print(f"nested loop took: {time.time() - start:.4f}s")
