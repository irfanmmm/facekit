import difflib
import os
import google.generativeai as genai
import json

class AIService:
    """
    Advanced AI Service with aligned side-by-side diffing and multi-file support.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        else:
            self.model = None

    def _align_codes(self, original, modified):
        """Aligns two versions of code for side-by-side display."""
        orig_lines = original.splitlines()
        mod_lines = modified.splitlines()
        s = difflib.SequenceMatcher(None, orig_lines, mod_lines)
        
        aligned_orig = []
        aligned_mod = []
        
        for tag, i1, i2, j1, j2 in s.get_opcodes():
            if tag == 'equal':
                for i in range(i1, i2):
                    aligned_orig.append({"text": orig_lines[i], "type": "equal"})
                    aligned_mod.append({"text": mod_lines[j1 + (i - i1)], "type": "equal"})
            elif tag == 'replace':
                # Removal then Addition to keep them distinct
                for i in range(i1, i2):
                    aligned_orig.append({"text": orig_lines[i], "type": "removed"})
                    aligned_mod.append({"text": "", "type": "empty"})
                for j in range(j1, j2):
                    aligned_orig.append({"text": "", "type": "empty"})
                    aligned_mod.append({"text": mod_lines[j], "type": "added"})
            elif tag == 'delete':
                for i in range(i1, i2):
                    aligned_orig.append({"text": orig_lines[i], "type": "removed"})
                    aligned_mod.append({"text": "", "type": "empty"})
            elif tag == 'insert':
                for j in range(j1, j2):
                    aligned_orig.append({"text": "", "type": "empty"})
                    aligned_mod.append({"text": mod_lines[j], "type": "added"})
        
        return aligned_orig, aligned_mod

    def _get_reference_context(self):
        references = {}
        core_files = ["model/client_settings.py", "utility/settings.py", "face_match/face_ml.py"]
        for path in core_files:
            try:
                if os.path.exists(path):
                    with open(path, 'r') as f: references[path] = f.read()
            except: pass
        return references

    def generate_code_change(self, prompt, target_file_path):
        if not self.model: return {"error": "API Key missing."}

        try:
            with open(target_file_path, 'r') as f: original_target = f.read()
            settings_path = "utility/settings.py"
            with open(settings_path, 'r') as f: original_settings = f.read()
        except Exception as e: return {"error": str(e)}

        references = self._get_reference_context()
        ref_text = "\n\n".join([f"FILE: {p}\n{c}" for p, c in references.items()])

        system_prompt = f"""
        You are a senior Facekit developer. 
        TASK: Modify {target_file_path} based on prompt.
        RULES:
        1. Multi-tenancy: Use `company_code`.
        2. Feature Flags: Wrap new logic in `Settings.get_setting(company_code, "Flag Name")`.
        3. Settings: If a flag is added, you MUST return the updated content of `utility/settings.py`.
        
        RESPONSE: JSON ONLY
        {{
           "modified_target": "full content of target file",
           "modified_settings": "full content of settings.py (optional)",
           "explanation": "...",
           "test_cases": []
        }}
        
        CONTEXT:
        {ref_text}
        """

        try:
            response = self.model.generate_content(f"{system_prompt}\n\nUSER PROMPT: {prompt}")
            res = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
            
            file_evolutions = []
            
            # Process Target File
            t_orig, t_mod = self._align_codes(original_target, res["modified_target"])
            file_evolutions.append({
                "file_path": target_file_path,
                "original_aligned": t_orig,
                "modified_aligned": t_mod,
                "is_target": True
            })
            
            # Process Settings File if changed
            if res.get("modified_settings"):
                s_orig, s_mod = self._align_codes(original_settings, res["modified_settings"])
                file_evolutions.append({
                    "file_path": "utility/settings.py",
                    "original_aligned": s_orig,
                    "modified_aligned": s_mod,
                    "is_target": False
                })
            
            return {
                "file_evolutions": file_evolutions,
                "explanation": res["explanation"],
                "test_cases": res["test_cases"],
                "modified_target_code": res["modified_target"],
                "modified_settings_code": res.get("modified_settings")
            }
        except Exception as e:
            return {"error": f"AI Evolution failed: {str(e)}"}
