import os
import re
from collections import defaultdict

def get_dashboard_stats():
    log_file = "logs/facekit.log"
    # Fallback if log file is missing or rotated
    if not os.path.exists(log_file):
        return {"dates": [], "success": [], "failures": []}
        
    stats = defaultdict(lambda: {"success": 0, "failures": 0})
    
    with open(log_file, "r") as f:
        for line in f:
            # We specifically look for the face match comparisons
            if "/compare-face" in line and "REQUEST" in line and "BODY:" in line:
                # Match the beginning of the log line to extract the date (YYYY-MM-DD)
                match = re.match(r"^(\d{4}-\d{2}-\d{2})", line)
                if match:
                    date_str = match.group(1)
                    
                    # Basic check for success in the response body payload
                    if '"message": "success"' in line or '"message":"success"' in line or "'message': 'success'" in line:
                        stats[date_str]["success"] += 1
                    else:
                        stats[date_str]["failures"] += 1
                        
    # Sort the dates chronologically
    sorted_dates = sorted(stats.keys())
    
    # Format the payload perfectly for frontend graphing libraries like Chart.js or ApexCharts
    result = {
        "dates": sorted_dates,
        "success": [stats[d]["success"] for d in sorted_dates],
        "failures": [stats[d]["failures"] for d in sorted_dates],
        "total_requests": sum(stats[d]["success"] + stats[d]["failures"] for d in sorted_dates)
    }
    
    return result
