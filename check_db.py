from model.database import get_database
db = get_database("A100")
doc = db['encodings_A100'].find_one()
if doc:
    enc = doc.get('encodings', [])
    if enc:
        if isinstance(enc[0], list):
            vec = enc[0]
        else:
            vec = enc
        print(f"Vector length: {len(vec)}")
        import numpy as np
        print(f"Norm: {np.linalg.norm(vec)}")
        print(f"First 5 values: {vec[:5]}")
    else:
        print("No encodings array")
else:
    print("No docs")
