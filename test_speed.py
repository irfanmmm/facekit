import re
from datetime import datetime

log_file = "logs/facekit.log"
reqs = {}
diffs = []
success_diffs = []

with open(log_file, "r") as f:
    for line in f:
        if "/compare-face" in line:
            match = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) .* USER_IP \| ([\d\.]+) .* BODY: (.*)", line)
            if match:
                dt_str = match.group(1)
                ip = match.group(2)
                body = match.group(3)
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S,%f")
                
                # if request
                if "'base64': '<REMOVED>'" in body or "'base64':" in body:
                    reqs[ip] = dt
                elif ip in reqs:
                    diff = (dt - reqs[ip]).total_seconds()
                    diffs.append(diff)
                    if '"message":"success"' in body or '"message": "success"' in body:
                        success_diffs.append(diff)
                    del reqs[ip]

print(f"Total API calls parsed: {len(diffs)}")
if diffs:
    print(f"Average speed (all requests): {sum(diffs)/len(diffs):.3f} seconds")
if success_diffs:
    print(f"Average speed (successful matches): {sum(success_diffs)/len(success_diffs):.3f} seconds")
