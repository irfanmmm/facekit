from flask import request, g
from model.client_settings import ClientSettingsModel
from functools import wraps

settings_model = ClientSettingsModel()

def inject_settings(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # client_id is typically the compony_code in this application
        # It can be in request.user (from jwt_required) or in headers/params
        client_id = None
        
        if hasattr(request, 'user') and request.user:
            client_id = request.user.get('compony_code')
        
        if not client_id:
            client_id = request.headers.get('X-Client-ID') or request.args.get('client_id')

        if client_id:
            settings = settings_model.get_settings(client_id)
            if not settings:
                # Create default if not exists
                settings = settings_model.create_default_settings(client_id)
            
            # Attach to request as requested (using state-like object or just request)
            # In Flask we can use g or request
            g.settings = settings
            request.settings = settings
        
        return f(*args, **kwargs)
    return decorated
