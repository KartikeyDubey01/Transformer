import json
import logging
from typing import List, Dict, Any, Union, Optional
from . import BaseSource
from ..normalizers import normalize_email, normalize_phone, normalize_link, normalize_date, normalize_skill

logger = logging.getLogger(__name__)

ATS_MAP = {
    "applicant_name": "raw_name",
    "contact_email": "email",
    "mobile": "phone",
    "employer": "company",
    "job_title": "title",
    "city": "city",
    "country_code": "country",
    "profile_linkedin": "linkedin",
    "profile_github": "github",
    "tech_skills": "skills",
    "work_history": "work_history",
    "academic": "education",
    "years_exp": "years_experience",
    "summary": "headline"
}

class ATSJsonSource(BaseSource):
    def __init__(self, filepath: str):
        self.filepath = filepath

    @staticmethod
    def _looks_corrupt(name: str) -> bool:
        if not name:
            return True
        if "_" in name and any(word.isupper() for word in name.split("_")):
            return True
        return False

    def _process_record(self, raw_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        mapped_record = {}
        for k, v in raw_record.items():
            norm_key = ATS_MAP.get(k, k)
            mapped_record[norm_key] = v

        raw_name = mapped_record.get("raw_name")
        if not raw_name or self._looks_corrupt(raw_name):
            logger.warning(f"Skipping corrupt entry in {self.filepath}: {raw_name}")
            return None

        cir = self.empty_cir(self.filepath, "ats_json")
        cir["raw_name"] = raw_name

        email = normalize_email(mapped_record.get("email"))
        if email:
            cir["emails"].append(email)

        phone = normalize_phone(mapped_record.get("phone"))
        if phone:
            cir["phones"].append(phone)

        city = mapped_record.get("city")
        if city:
            cir["location"]["city"] = city
        country = mapped_record.get("country")
        if country:
            cir["location"]["country"] = country

        linkedin = normalize_link(mapped_record.get("linkedin"))
        if linkedin:
            cir["links"]["linkedin"] = linkedin

        github = normalize_link(mapped_record.get("github"))
        if github:
            cir["links"]["github"] = github

        headline = mapped_record.get("headline")
        if headline:
            cir["headline"] = headline

        years_exp = mapped_record.get("years_experience")
        if years_exp is not None:
            try:
                y = float(years_exp)
                if 0 <= y <= 60:
                    cir["years_experience"] = y
            except (ValueError, TypeError):
                pass

        skills = mapped_record.get("skills", [])
        if isinstance(skills, list):
            norm_skills = []
            seen = set()
            for s in skills:
                ns = normalize_skill(s)
                if ns and ns.lower() not in seen:
                    seen.add(ns.lower())
                    norm_skills.append(ns)
            cir["skills"] = norm_skills
        elif isinstance(skills, str):
            ns = normalize_skill(skills)
            if ns:
                cir["skills"] = [ns]

        work_history = mapped_record.get("work_history", [])
        if isinstance(work_history, list):
            for job in work_history:
                if isinstance(job, dict):
                    cir["experience"].append({
                        "company": job.get("org") or job.get("company"),
                        "title": job.get("role") or job.get("title"),
                        "start": normalize_date(job.get("from") or job.get("start")),
                        "end": normalize_date(job.get("to") or job.get("end")),
                        "summary": None
                    })

        # Single company/title fallback
        if not work_history:
            company = mapped_record.get("company")
            title = mapped_record.get("title")
            if company or title:
                 cir["experience"].append({
                     "company": company,
                     "title": title,
                     "start": None,
                     "end": None,
                     "summary": None
                 })

        academic = mapped_record.get("education", [])
        if isinstance(academic, list):
            for edu in academic:
                if isinstance(edu, dict):
                    year_val = edu.get("year")
                    year_str = str(year_val) if year_val else None
                    if year_str and len(year_str) == 4 and year_str.isdigit():
                        # The schema just expects the raw year or formatted date, we can just leave it as year if that's what we have, but schema doesn't specify normalize_date for education end_year. Let's just put it in.
                        end_year = year_str
                    else:
                        end_year = normalize_date(year_str) if year_str else None
                    
                    cir["education"].append({
                        "institution": edu.get("school") or edu.get("institution"),
                        "degree": edu.get("degree"),
                        "field": edu.get("subject") or edu.get("field"),
                        "end_year": end_year
                    })

        return cir

    def extract(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, dict):
                data = [data]
                
            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        cir = self._process_record(record)
                        if cir:
                            results.append(cir)
        except Exception as e:
            logger.error(f"Failed to read JSON {self.filepath}: {e}")

        return results
