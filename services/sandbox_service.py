import os
import shutil
import tempfile
import subprocess
import secrets

class SandboxService:
    """
    Isolated environment to test AI-generated code changes.
    """
    def __init__(self, project_root):
        self.project_root = project_root

    def run_validation(self, file_changes):
        """
        Clones the project and applies multiple file changes (full content overwrites).
        'file_changes' is a dict: { "relative/path/to/file.py": "full content..." }
        """
        sandbox_dir = tempfile.mkdtemp(prefix="facekit_sandbox_")
        
        try:
            # 1. Copy project to sandbox
            def ignore_dirs(path, names):
                return [n for n in names if n in ['.venv', '__pycache__', 'logs', 'uploads', '.git']]
            
            shutil.copytree(self.project_root, sandbox_dir, ignore=ignore_dirs, dirs_exist_ok=True)
            
            # 2. Apply all file changes (Overwrites)
            for file_path, new_content in file_changes.items():
                abs_path = os.path.join(sandbox_dir, file_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w") as f:
                    f.write(new_content)
            
            # 3. Lint check (Compilation)
            lint_process = subprocess.run(
                ["python3", "-m", "compileall", "."],
                cwd=sandbox_dir,
                capture_output=True,
                text=True
            )
            
            if lint_process.returncode != 0:
                return {
                    "success": False,
                    "stage": "linting",
                    "error": lint_process.stderr or "Syntax errors detected in changes."
                }

            # 4. Run Tests (pytest)
            test_process = subprocess.run(
                ["pytest", "--maxfail=1"],
                cwd=sandbox_dir,
                capture_output=True,
                text=True
            )
            
            is_success = test_process.returncode in [0, 5] # 0: success, 5: no tests found
            
            return {
                "success": is_success,
                "stage": "testing",
                "stdout": test_process.stdout,
                "stderr": test_process.stderr,
                "logs": "Sandbox validation passed." if is_success else "Tests failed in sandbox"
            }

        except Exception as e:
            return {
                "success": False,
                "stage": "sandbox_error",
                "error": str(e)
            }
        finally:
            # We keep the sandbox for a moment if you want to preview, 
            # but usually we should clean up.
            # shutil.rmtree(sandbox_dir)
            pass
