# gunicorn_config.py
import logging
import os


workers = 1
threads = 1
timeout = 300
keepalive = 30
graceful_timeout = 60
bind = "0.0.0.0:5001"
worker_class = "gthread"  # use gthread if majority is I/O; process workers for CPU-bound
preload_app = False       # IMPORTANT: do not preload app if native libs are not fork-safe
accesslog = "/home/ec2-user/facekit/facekit/logs/access.log"
errorlog = "/home/ec2-user/facekit/facekit/logs/error.log"

def post_fork(server, worker):
    """Called in the worker process after fork — safe place to init FAISS."""
    try:
        from face_match import init_faiss_indexes
        server.log.info("Worker post_fork: initializing FAISS indexes")
        init_faiss_indexes()
        server.log.info("Worker post_fork: FAISS initialized")
    except Exception as e:
        server.log.exception("Failed to init FAISS in post_fork: %s", e)

# sudo systemctl restart facekit@5001
# sudo systemctl restart facekit@5002
# sudo systemctl restart facekit@5003
