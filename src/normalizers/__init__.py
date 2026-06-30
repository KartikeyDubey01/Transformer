import re
import hashlib
from typing import Optional, List

SKILL_ALIASES = {
    "python": "Python",
    "py": "Python",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "golang": "Go",
    "go": "Go",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "docker": "Docker",
    "aws": "AWS",
    "gcp": "Google Cloud",
    "google cloud": "Google Cloud",
}

COUNTRY_LOOKUP = {
    "india": "IN",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "gb": "GB",
    "canada": "CA",
    "ca": "CA",
    "australia": "AU",
    "au": "AU",
    "germany": "DE",
    "de": "DE",
    "france": "FR",
    "fr": "FR",
    "japan": "JP",
    "jp": "JP",
    "china": "CN",
    "cn": "CN",
    "brazil": "BR",
    "br": "BR",
}

DIAL_CODE = {
    "IN": "+91",
    "US": "+1",
    "GB": "+44",
    "CA": "+1",
    "AU": "+61",
}

def normalize_email(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.lower().strip()
    if re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", cleaned):
        return cleaned
    return None

def normalize_phone(raw: Optional[str], country_hint: Optional[str] = None) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    # Strip non-digits except +
    cleaned = re.sub(r"[^\d+]", "", raw)
    if not cleaned:
        return None
        
    if cleaned.startswith("+"):
        if 7 <= len(cleaned) - 1 <= 15:
            return cleaned
        return None
        
    # No +, prepend country dial code if we have a hint and it's a 10-digit number
    if country_hint and len(cleaned) == 10:
        norm_country = normalize_country(country_hint)
        if norm_country and norm_country in DIAL_CODE:
            return f"{DIAL_CODE[norm_country]}{cleaned}"
            
    # If no valid E.164 can be formed but it has digits, we'll return None 
    # as per E.164 requirements unless it is exactly matching a format.
    # Actually prompt says: "If has +, validate length [7-15]. If country hint, prepend dial code for 10-digit locals."
    # If neither, and it's just raw numbers, maybe we just return it if it looks like a number, or return None.
    # We will return None if it doesn't start with + after our processing, except if it's already 10+ digits?
    # Let's say if no `+` is present, it's invalid unless hint provides it. But wait, what if it's 0014155550192?
    # Some numbers start with 00. We can replace 00 with +.
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
        if 7 <= len(cleaned) - 1 <= 15:
            return cleaned
    return None

def normalize_skill(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    lower_key = cleaned.lower()
    if lower_key in SKILL_ALIASES:
        return SKILL_ALIASES[lower_key]
    return cleaned.title()

def normalize_skills(raw_list: Optional[str]) -> List[str]:
    if not raw_list or not isinstance(raw_list, str):
        return []
    # Split by comma or pipe
    parts = re.split(r"[,|]", raw_list)
    skills = []
    seen = set()
    for part in parts:
        norm = normalize_skill(part)
        if norm:
            lower_norm = norm.lower()
            if lower_norm not in seen:
                seen.add(lower_norm)
                skills.append(norm)
    return skills

def normalize_country(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.lower().strip()
    if cleaned in COUNTRY_LOOKUP:
        return COUNTRY_LOOKUP[cleaned]
    return None

def normalize_date(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    if cleaned in ("present", "current"):
        return None
        
    # YYYY-MM
    if re.match(r"^\d{4}-\d{2}$", cleaned):
        return cleaned
        
    # MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{4})$", cleaned)
    if m:
        month = m.group(1).zfill(2)
        return f"{m.group(2)}-{month}"
        
    # Month YYYY (e.g. Mar 2021, march 2021)
    m = re.match(r"^([a-z]+)\s+(\d{4})$", cleaned)
    if m:
        month_str = m.group(1)[:3]
        months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                  "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
        if month_str in months:
            return f"{m.group(2)}-{months[month_str]}"
            
    # YYYY
    if re.match(r"^\d{4}$", cleaned):
        return f"{cleaned}-01"
        
    return None

def normalize_link(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        return f"https://{cleaned}"
    if cleaned.startswith("http://"):
        return "https://" + cleaned[7:]
    return cleaned

def generate_candidate_id(name: str, emails: List[str]) -> str:
    name_clean = name.lower() if name else ""
    first_email = emails[0].lower() if emails else ""
    hash_input = f"{name_clean}|{first_email}".encode('utf-8')
    sha_hash = hashlib.sha1(hash_input).hexdigest()[:12]
    return f"cand_{sha_hash}"
