#!/usr/bin/env python3
import os
import sys

# Add parent directory to sys.path to import model.database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.database import get_database


def audit_dimensions():
    print("🔍 Starting audit of encoding vector dimensions across all companies...\n")
    client = get_database()
    dbs = client.list_database_names()


    ignore_dbs = {"admin", "config", "local", "AppVersion"}

    for db_name in dbs:
        if db_name in ignore_dbs:
            continue

        db = client[db_name]

        collections = db.list_collection_names()

        enc_collections = [c for c in collections if c.startswith("encodings_")]
        for col_name in enc_collections:
            company_code = col_name.replace("encodings_", "")
            print(f"==================================================")
            print(f"🏢 Company Code / Database: {company_code} ({db_name})")
            print(f"==================================================")

            col = db[col_name]
            cursor = col.find({"is_delete": {"$ne": True}})

            total_docs = 0
            dimension_counts = {}
            flagged_employees = []

            for doc in cursor:
                total_docs += 1
                emp_code = doc.get("employee_code", doc.get("fullname", str(doc.get("_id"))))
                enc_data = doc.get("encodings")

                if not enc_data:
                    dimension_counts["NO_ENCODING"] = dimension_counts.get("NO_ENCODING", 0) + 1
                    flagged_employees.append((emp_code, "NO_ENCODING"))
                    continue

                poses = enc_data if isinstance(enc_data[0], list) else [enc_data]

                for p_idx, pose in enumerate(poses):
                    dim = len(pose) if isinstance(pose, list) else "UNKNOWN"
                    dimension_counts[dim] = dimension_counts.get(dim, 0) + 1

                    if dim != 128:
                        flagged_employees.append((emp_code, f"Pose {p_idx + 1}: {dim}-d"))

            print(f"Total Active Employees: {total_docs}")
            print("Encoding Vector Dimension Breakdown:")
            for dim, count in dimension_counts.items():
                status = "✅ VALID" if dim == 128 else "⚠️ NEEDS RE-ENROLLMENT"
                print(f"  - {dim}-dimensional: {count} vectors [{status}]")

            if flagged_employees:
                print(f"\n⚠️ Employees needing re-enrollment (Non 128-d):")
                for emp, reason in flagged_employees:
                    print(f"  - Employee: {emp} ({reason})")
            else:
                print("\n✅ All employee encodings are 100% compliant 128-d vectors.")
            print("\n")


if __name__ == "__main__":
    audit_dimensions()
