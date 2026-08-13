import time
emp_codes_set = {str(i) for i in range(50000)}
filenames = [f"user_{i}.jpg" for i in range(2000)]
start = time.time()
image_map = {}
for filename in filenames:
    full_name = filename.lower()
    for emp_code in list(emp_codes_set):
        if emp_code and emp_code in full_name:
            image_map[emp_code] = filename
            emp_codes_set.remove(emp_code)
            break
    if not emp_codes_set:
        break
print(f"Took {time.time() - start:.2f} seconds")
