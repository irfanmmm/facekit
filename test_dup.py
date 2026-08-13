import sys
sys.path.append('.')
from face_match.faiss_manager import FaceIndexManager
import numpy as np

cashe = FaceIndexManager('A140')
print("Total elements:", cashe.index.ntotal if cashe.index else 0)
