import re
import logging
from typing import List, Dict, Any, Optional
from . import BaseSource
from ..normalizers import normalize_email, normalize_phone, normalize_link, normalize_skill, SKILL_ALIASES

logger = logging.getLogger(__name__)

EMAIL_RE = r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
PHONE_RE = r"(?:\+?[\d\-\s().]{7,20})"
LINKEDIN_RE = r"linkedin\.com/in/[\w\-]+"
GITHUB_RE = r"github\.com/[\w\-]+"
YEARS_EXP_RE = r"(\d+)[\+\-]?\s*(?:year|yr)s?\s*(?:of\s+)?(?:total\s+)?experience"
NAME_RE = r"^(?:Candidate|Name)[:\s]+(.+)$"

# Sort skill aliases by length descending to match longest first (e.g. "machine learning" before "machine")
_sorted_skills = sorted(SKILL_ALIASES.keys(), key=len, reverse=True)
SKILL_DETECTION_RE = r"\b(" + r"|".join(re.escape(k) for k in _sorted_skills) + r")\b"

class RecruiterNotesSource(BaseSource):
    def __init__(self, filepath: str):
        self.filepath = filepath

    def _extract_name(self, block: str) -> Optional[str]:
        # Try explicit name first
        for line in block.splitlines():
            m = re.match(NAME_RE, line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
                
        # Fallback: first line that is 2-4 words and all words start with uppercase
        for line in block.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue
            words = clean_line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                return clean_line
        return None

    def _process_block(self, block: str) -> Optional[Dict[str, Any]]:
        if not block.strip():
            return None
            
        raw_name = self._extract_name(block)
        if not raw_name:
            return None
            
        cir = self.empty_cir(self.filepath, "nlp_regex")
        cir["raw_name"] = raw_name
        
        # Emails
        for m in re.finditer(EMAIL_RE, block):
            email = normalize_email(m.group(0))
            if email and email not in cir["emails"]:
                cir["emails"].append(email)
                
        # Phones
        for m in re.finditer(PHONE_RE, block):
            raw_phone = m.group(0)
            digits_only = re.sub(r"\D", "", raw_phone)
            if len(digits_only) >= 7:
                phone = normalize_phone(raw_phone)
                if phone and phone not in cir["phones"]:
                    cir["phones"].append(phone)
                    
        # Links
        for m in re.finditer(LINKEDIN_RE, block, re.IGNORECASE):
            link = normalize_link(m.group(0))
            if link and not cir["links"]["linkedin"]:
                cir["links"]["linkedin"] = link
                
        for m in re.finditer(GITHUB_RE, block, re.IGNORECASE):
            link = normalize_link(m.group(0))
            if link and not cir["links"]["github"]:
                cir["links"]["github"] = link
                
        # Years Experience
        exp_match = re.search(YEARS_EXP_RE, block, re.IGNORECASE)
        if exp_match:
            try:
                cir["years_experience"] = float(exp_match.group(1))
            except ValueError:
                pass
                
        # Skills
        seen_skills = set()
        for m in re.finditer(SKILL_DETECTION_RE, block, re.IGNORECASE):
            raw_skill = m.group(1)
            norm_skill = normalize_skill(raw_skill)
            if norm_skill and norm_skill.lower() not in seen_skills:
                seen_skills.add(norm_skill.lower())
                cir["skills"].append(norm_skill)
                
        # If block looks like corrupt entry with no useful data (other than name), maybe skip
        # Let's check if there is any other data
        has_data = bool(cir["emails"] or cir["phones"] or cir["links"]["linkedin"] or cir["links"]["github"] or cir["skills"] or cir["years_experience"] is not None)
        if not has_data:
            logger.warning(f"Skipping block in {self.filepath}: no useful data found for {raw_name}")
            return None
            
        return cir

    def extract(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            blocks = re.split(r"\n---\n", content)
            for block in blocks:
                cir = self._process_block(block)
                if cir:
                    results.append(cir)
        except Exception as e:
            logger.error(f"Failed to read TXT {self.filepath}: {e}")
            
        return results
