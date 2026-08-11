from model.database import _get_client
client = _get_client()
print([c for c in client["A100"].list_collection_names() if 'punch' in c.lower() or 'attend' in c.lower() or 'log' in c.lower()])
