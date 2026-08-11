from model.database import _get_client
client = _get_client()
doc = client["A100"]["encodings_A100"].find_one({"encodings_v2": {"$exists": True}})
print(doc.keys() if doc else "No doc")
