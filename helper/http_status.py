import http

class HTTPStatusHelper:
    """Helper to convert HTTP status codes to messages."""
    status_map = {status.value: status.phrase for status in http.HTTPStatus}