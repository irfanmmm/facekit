import csv

input_file = '/home/ubuntu/facekit/facekit/branches_details_A140.csv'
output_file = '/home/ubuntu/facekit/facekit/branches_details_merged_A140.csv'

seen_names = set()
merged_rows = []

with open(input_file, mode='r', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        name = row['branchName'].strip()
        if name not in seen_names:
            seen_names.add(name)
            merged_rows.append(row)

with open(output_file, mode='w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(merged_rows)

print(f"Successfully processed {input_file} -> {output_file}")
print(f"Original rows: {reader.line_num - 1}")
print(f"Unique rows: {len(merged_rows)}")
