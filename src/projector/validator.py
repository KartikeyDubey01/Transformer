from typing import Dict, Any, List

class SchemaValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def validate(self, projected_profile: Dict[str, Any]) -> List[str]:
        issues = []
        on_missing = self.config.get("on_missing", "null")
        
        for field in self.config.get("fields", []):
            path = field.get("path")
            is_required = field.get("required", False)
            expected_type = field.get("type")
            
            val = projected_profile.get(path)
            
            if val is None:
                if is_required:
                    issues.append(f"Missing required field: {path}")
                elif on_missing == "error":
                    issues.append(f"Missing field with on_missing=error: {path}")
                continue
                
            if expected_type:
                if expected_type == "string" and not isinstance(val, str):
                    issues.append(f"Type mismatch for {path}: expected string, got {type(val).__name__}")
                elif expected_type == "number" and not isinstance(val, (int, float)):
                    issues.append(f"Type mismatch for {path}: expected number, got {type(val).__name__}")
                elif expected_type == "object" and not isinstance(val, dict):
                    issues.append(f"Type mismatch for {path}: expected object, got {type(val).__name__}")
                elif expected_type == "array" and not isinstance(val, list):
                    issues.append(f"Type mismatch for {path}: expected array, got {type(val).__name__}")
                elif expected_type == "string[]":
                    if not isinstance(val, list):
                        issues.append(f"Type mismatch for {path}: expected string[], got {type(val).__name__}")
                    elif not all(isinstance(v, str) for v in val):
                        issues.append(f"Type mismatch for {path}: expected string[], but elements are not all strings")
                        
        return issues
