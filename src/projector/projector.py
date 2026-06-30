import re
from typing import Dict, Any, List
from ..normalizers import normalize_phone, normalize_skill

class OutputProjector:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        return {
            "fields": [
                {"path": "candidate_id", "type": "string"},
                {"path": "full_name", "type": "string"},
                {"path": "emails", "type": "array"},
                {"path": "phones", "type": "array"},
                {"path": "location", "type": "object"},
                {"path": "links", "type": "object"},
                {"path": "headline", "type": "string"},
                {"path": "years_experience", "type": "number"},
                {"path": "skills", "type": "array"},
                {"path": "experience", "type": "array"},
                {"path": "education", "type": "array"}
            ],
            "include_confidence": True,
            "include_provenance": True,
            "on_missing": "null"
        }

    def _resolve(self, obj: Any, path: str) -> Any:
        if not path:
            return obj
            
        # Handle "full_name"
        if not ("." in path or "[" in path):
            if isinstance(obj, dict):
                return obj.get(path)
            return None
            
        # Tokenize path: "experience[0].company" -> ["experience", "[0]", "company"]
        # "skills[].name" -> ["skills", "[]", "name"]
        tokens = re.findall(r"([^[\].]+)|(\[[0-9]*\])", path)
        # tokens is list of tuples like [('experience', ''), ('', '[0]'), ('company', '')]
        
        current = obj
        for t1, t2 in tokens:
            token = t1 if t1 else t2
            
            if token.startswith("[") and token.endswith("]"):
                idx_str = token[1:-1]
                if not isinstance(current, list):
                    return None
                    
                if idx_str == "":
                    # Array mapping
                    # the remaining path should be mapped over this array
                    # We can cheat by resolving the rest of the path on each element
                    # But we need to find the rest of the path from tokens.
                    # This requires recursion or slicing tokens. It's easier to rebuild rest of path.
                    # Since we are iterating, we can just consume the rest.
                    # Let's rebuild the rest of the path to resolve recursively.
                    idx = tokens.index((t1, t2))
                    rest_tokens = tokens[idx+1:]
                    rest_path = ""
                    for r1, r2 in rest_tokens:
                        rt = r1 if r1 else r2
                        if rt.startswith("["):
                            rest_path += rt
                        else:
                            if rest_path and not rest_path.endswith("]"):
                                rest_path += "." + rt
                            elif rest_path and rest_path.endswith("]"):
                                rest_path += "." + rt
                            else:
                                rest_path += rt
                    
                    if not rest_path:
                        return current # "skills[]" -> return the list itself
                        
                    res = []
                    for item in current:
                        val = self._resolve(item, rest_path)
                        if val is not None:
                            res.append(val)
                    return res if res else None
                else:
                    try:
                        idx = int(idx_str)
                        if 0 <= idx < len(current):
                            current = current[idx]
                        else:
                            return None
                    except ValueError:
                        return None
            else:
                if isinstance(current, dict):
                    current = current.get(token)
                else:
                    return None
                    
        return current

    def project(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        
        on_missing = self.config.get("on_missing", "null")
        
        for field in self.config.get("fields", []):
            out_key = field.get("path")
            src_path = field.get("from", out_key)
            
            val = self._resolve(profile, src_path)
            
            norm = field.get("normalize")
            if val is not None and norm:
                if norm == "E164":
                    if isinstance(val, list):
                        new_val = []
                        for v in val:
                            nv = normalize_phone(v)
                            if nv: new_val.append(nv)
                        val = new_val if new_val else None
                    else:
                        val = normalize_phone(val)
                elif norm == "canonical":
                    if isinstance(val, list):
                        new_val = []
                        for v in val:
                            nv = normalize_skill(v)
                            if nv: new_val.append(nv)
                        val = new_val if new_val else None
                    else:
                        val = normalize_skill(val)
                        
            if val is None:
                if on_missing == "omit":
                    continue
                elif on_missing == "error":
                    # handled in validator, but we can just set it to None here
                    result[out_key] = None
                else: # "null"
                    result[out_key] = None
            else:
                result[out_key] = val
                
        if self.config.get("include_confidence", False):
            result["overall_confidence"] = profile.get("overall_confidence")
            # If skills were projected, confidence for skills might need to be kept if we projected the whole skill object,
            # but if they mapped `skills[].name`, the confidence is lost. 
            # If `skills` wasn't overridden, it retains confidence.
            # We don't need to recursively strip confidence if include_confidence is false? 
            # The prompt says: "if false, strip overall_confidence and skills[].confidence".
            # The result currently only has what we put in it. If we put the full `skills` array, we might need to strip.
        else:
            if "skills" in result and isinstance(result["skills"], list):
                for skill in result["skills"]:
                    if isinstance(skill, dict) and "confidence" in skill:
                        del skill["confidence"]
                        
        if self.config.get("include_provenance", False):
            result["provenance"] = profile.get("provenance")
            
        return result
