from dateutil.parser import parse

def compute_working_seconds(log_details):
    logs = []
    for log in log_details:
        t = log.get("time")
        if isinstance(t, str):
            try:
                t = parse(t)
            except:
                continue
        logs.append({"direction": log.get("direction"), "time": t})

    logs.sort(key=lambda x: x["time"])
    total = 0
    in_time = None

    for log in logs:
        if log["direction"] == "in":
            in_time = log["time"]
        elif log["direction"] == "out" and in_time:
            total += (log["time"] - in_time).total_seconds()
            in_time = None

    return total

def format_duration(seconds):
    try:
        seconds = int(seconds)
    except:
        return "00:00:00"

    if seconds < 0:
        seconds = 0

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    return f' {hours:02}:{minutes:02}:{secs:02}'

