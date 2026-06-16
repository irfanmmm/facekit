from flask import Blueprint, request, jsonify
from auth.controller import jwt_required
import os
from services.ai_service import AIService
from services.sandbox_service import SandboxService

evolution_bp = Blueprint('evolution', __name__)
ai_service = AIService()
sandbox_service = SandboxService(os.getcwd())

@evolution_bp.route('/suggest-change', methods=['POST'])
@jwt_required
def suggest_change():
    data = request.get_json()
    prompt = data.get("prompt")
    target_file = data.get("target_file", "face_match/face_ml.py")
    
    if not prompt: return jsonify({"error": "Prompt required"}), 400

    suggestion = ai_service.generate_code_change(prompt, target_file)
    if "error" in suggestion: return jsonify({"status": "error", "message": suggestion["error"]}), 500

    # Sandbox Validation
    file_changes = { target_file: suggestion["modified_target_code"] }
    if suggestion.get("modified_settings_code"):
        file_changes["utility/settings.py"] = suggestion["modified_settings_code"]

    sandbox_result = sandbox_service.run_validation(file_changes)
    
    return jsonify({
        "status": "success_v4",
        "suggestion": {
            "file_evolutions": suggestion["file_evolutions"],
            "explanation": suggestion["explanation"],
            "test_cases": suggestion["test_cases"]
        },
        "sandbox_result": sandbox_result
    })

@evolution_bp.route('/apply-change', methods=['POST'])
@jwt_required
def apply_change():
    # In a real app, apply logic here...
    return jsonify({"status": "applied"})
