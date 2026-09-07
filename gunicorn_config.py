# gunicorn_config.py
import logging
import os


workers = 3
threads = 2
timeout = 300
keepalive = 30
graceful_timeout = 60
# bind = "0.0.0.0:5001"
# This box has only 2 vCPUs (nproc=2), and confirmed by direct observation a
# single face-scan request (YuNet + SFace + MediaPipe) can peg one entire
# core by itself — this workload is CPU-bound, not I/O-bound. threads=4 (was
# tuned assuming I/O-wait overlap, e.g. Mongo/OfficeKit) let up to 3*4=12
# CPU-heavy jobs start concurrently on just 2 cores: instead of the first
# arrivals finishing quickly and later ones queuing briefly, every concurrent
# request got a thin slice of CPU and ALL of them ran slow together. threads=2
# (3*2=6 total slots) still gives headroom to overlap genuine I/O waits
# (Mongo queries, the OfficeKit SQL Server call) without admitting so many
# simultaneous CPU jobs that they all degrade each other.
worker_class = "gthread"
preload_app = False       # IMPORTANT: do not preload app if native libs are not fork-safe
accesslog = "/home/ubuntu/facekit/facekit/logs/access.log"
errorlog = "/home/ubuntu/facekit/facekit/logs/error.log"

def post_fork(server, worker):
    """Called in the worker process after fork — safe place to init FAISS.

    Also eagerly loads the YuNet/SFace/MediaPipe models here. Previously these
    were lazy-loaded on each singleton's first real request, so every worker
    restart (including the crash-respawns we've seen from the OfficeKit
    connection bug) made the next unlucky user pay for loading three ML
    models synchronously inside their own request. Loading them now, during
    startup instead of during a live request, removes that per-restart cold
    start entirely.
    """
    try:
        from face_match import init_faiss_indexes
        server.log.info("Worker post_fork: initializing FAISS indexes")
        init_faiss_indexes()
        server.log.info("Worker post_fork: FAISS initialized")
    except Exception as e:
        server.log.exception("Failed to init FAISS in post_fork: %s", e)

    try:
        from face_match.face_ml import _get_yunet_detector, _get_sface_recognizer, _get_face_landmarker
        server.log.info("Worker post_fork: pre-loading YuNet/SFace/MediaPipe models")
        _get_yunet_detector()
        _get_sface_recognizer()
        _get_face_landmarker()
        server.log.info("Worker post_fork: ML models pre-loaded")
    except Exception as e:
        server.log.exception("Failed to pre-load ML models in post_fork: %s", e)

# sudo systemctl restart facekit@5001
# sudo systemctl restart facekit@5002
# sudo systemctl restart facekit@5003
