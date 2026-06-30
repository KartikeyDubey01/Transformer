import csv
import logging
from typing import List, Dict, Any
from . import BaseSource
from ..normalizers import normalize_email, normalize_phone, normalize_skills, normalize_link

logger = logging.getLogger(__name__)

FIELD_MAP = {
    "name": "raw_name",
    "full_name": "raw_name",
    "candidate_name": "raw_name",
    "email": "email",
    "email_address": "email",
    "contact_email": "email",
    "phone": "phone",
    "mobile": "phone",
    "current_company": "company",
    "company": "company",
    "employer": "company",
    "title": "title",
    "job_title": "title",
    "position": "title",
    "location": "location_raw",
    "linkedin": "linkedin",
    "linkedin_url": "linkedin",
    "github": "github",
    "github_url": "github",
    "skills": "skills_raw",
    "tech_skills": "skills_raw",
}

class CSVSource(BaseSource):
    def __init__(self, filepath: str):
        self.filepath = filepath

    @staticmethod
    def _parse_city_from_location(location_raw: str) -> str:
        if not location_raw:
            return None
        parts = location_raw.split()
        return parts[0] if parts else None

    @staticmethod
    def _parse_country_from_location(location_raw: str) -> str:
        if not location_raw:
            return None
        parts = location_raw.split()
        return parts[-1] if len(parts) > 1 else (parts[0] if parts else None)

    def extract(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with open(self.filepath, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return results
                
                # Normalize headers
                normalized_headers = {}
                for field in reader.fieldnames:
                    clean_field = field.lower().strip() if field else ""
                    if clean_field in FIELD_MAP:
                        normalized_headers[field] = FIELD_MAP[clean_field]
                    else:
                        normalized_headers[field] = clean_field
                
                for row_idx, row in enumerate(reader):
                    mapped_row = {}
                    for k, v in row.items():
                        norm_key = normalized_headers.get(k)
                        if norm_key:
                            mapped_row[norm_key] = v.strip() if v else None
                    
                    if not mapped_row.get("raw_name"):
                        logger.warning(f"Skipping row {row_idx + 1} in {self.filepath}: No name found")
                        continue
                        
                    cir = self.empty_cir(self.filepath, "csv_row")
                    cir["raw_name"] = mapped_row.get("raw_name")
                    
                    email = normalize_email(mapped_row.get("email"))
                    if email:
                        cir["emails"].append(email)
                        
                    phone = normalize_phone(mapped_row.get("phone"))
                    if phone:
                        cir["phones"].append(phone)
                        
                    loc_raw = mapped_row.get("location_raw")
                    if loc_raw:
                        cir["location"]["city"] = self._parse_city_from_location(loc_raw)
                        cir["location"]["country"] = self._parse_country_from_location(loc_raw)
                        
                    linkedin = normalize_link(mapped_row.get("linkedin"))
                    if linkedin:
                        cir["links"]["linkedin"] = linkedin
                        
                    github = normalize_link(mapped_row.get("github"))
                    if github:
                        cir["links"]["github"] = github
                        
                    skills_raw = mapped_row.get("skills_raw")
                    if skills_raw:
                        cir["skills"] = normalize_skills(skills_raw)
                        
                    company = mapped_row.get("company")
                    title = mapped_row.get("title")
                    if company or title:
                        cir["experience"].append({
                            "company": company,
                            "title": title,
                            "start": None,
                            "end": None,
                            "summary": None
                        })
                        
                    results.append(cir)
        except Exception as e:
            logger.error(f"Failed to read CSV {self.filepath}: {e}")
            
        return results
