import re
from typing import List, Dict, Any
from ..normalizers import generate_candidate_id, normalize_skill

SOURCE_PRIORITY = ["csv_row", "ats_json", "nlp_regex"]

class CandidateMerger:
    @staticmethod
    def _normalize_name_key(name: str) -> str:
        if not name:
            return ""
        return re.sub(r"[^a-z\s]", "", name.lower()).strip()

    @staticmethod
    def _source_rank(method: str) -> int:
        if method in SOURCE_PRIORITY:
            return SOURCE_PRIORITY.index(method)
        return len(SOURCE_PRIORITY)

    @staticmethod
    def _record_prov(provenance: List[Dict[str, str]], field: str, source: str, method: str):
        provenance.append({
            "field": field,
            "source": source,
            "method": method
        })

    def group_cirs(self, cirs: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        # Simple union-find or connected components
        # 1. Exact email match -> same group
        # 2. _normalize_name_key(name) = ... -> same group
        
        # We can build a graph where nodes are indices of CIRs
        # Edges if they share an email or a normalized name key
        
        n = len(cirs)
        adj = {i: set() for i in range(n)}
        
        email_to_idx = {}
        name_to_idx = {}
        
        for i, cir in enumerate(cirs):
            name_key = self._normalize_name_key(cir.get("raw_name", ""))
            if name_key:
                if name_key in name_to_idx:
                    for j in name_to_idx[name_key]:
                        adj[i].add(j)
                        adj[j].add(i)
                else:
                    name_to_idx[name_key] = []
                name_to_idx[name_key].append(i)
                
            for email in cir.get("emails", []):
                if email in email_to_idx:
                    for j in email_to_idx[email]:
                        adj[i].add(j)
                        adj[j].add(i)
                else:
                    email_to_idx[email] = []
                email_to_idx[email].append(i)
                
        visited = set()
        groups = []
        for i in range(n):
            if i not in visited:
                group = []
                queue = [i]
                visited.add(i)
                while queue:
                    curr = queue.pop(0)
                    group.append(cirs[curr])
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                groups.append(group)
                
        return groups

    def merge_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Sort group by source rank before merging (highest priority first)
        sorted_group = sorted(group, key=lambda c: self._source_rank(c["method"]))
        
        profile = {
            "full_name": None,
            "emails": [],
            "phones": [],
            "location": {"city": None, "region": None, "country": None},
            "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
            "headline": None,
            "years_experience": None,
            "skills": [], # List of Dict[str, Any] later
            "experience": [],
            "education": [],
            "provenance": [],
            "overall_confidence": 0.0,
            "candidate_id": None
        }
        
        prov = profile["provenance"]
        
        # Merge full_name
        for cir in sorted_group:
            if cir.get("raw_name") and not profile["full_name"]:
                profile["full_name"] = cir["raw_name"]
                self._record_prov(prov, "full_name", cir["source"], cir["method"])
                break
                
        # Merge emails
        seen_emails = set()
        for cir in sorted_group:
            for email in cir.get("emails", []):
                if email not in seen_emails:
                    seen_emails.add(email)
                    profile["emails"].append(email)
                    self._record_prov(prov, "emails", cir["source"], cir["method"])
                    
        # Merge phones
        seen_phones = set()
        for cir in sorted_group:
            for phone in cir.get("phones", []):
                if phone not in seen_phones:
                    seen_phones.add(phone)
                    profile["phones"].append(phone)
                    self._record_prov(prov, "phones", cir["source"], cir["method"])
                    
        # Merge links
        for link_type in ["linkedin", "github", "portfolio"]:
            for cir in sorted_group:
                link_val = cir.get("links", {}).get(link_type)
                if link_val and not profile["links"][link_type]:
                    profile["links"][link_type] = link_val
                    self._record_prov(prov, f"links.{link_type}", cir["source"], cir["method"])
                    break
                    
        # Merge location
        for loc_field in ["city", "region", "country"]:
            for cir in sorted_group:
                loc_val = cir.get("location", {}).get(loc_field)
                if loc_val and not profile["location"][loc_field]:
                    profile["location"][loc_field] = loc_val
                    self._record_prov(prov, f"location.{loc_field}", cir["source"], cir["method"])
                    break
                    
        # Merge headline
        for cir in sorted_group:
            if cir.get("headline") and not profile["headline"]:
                profile["headline"] = cir["headline"]
                self._record_prov(prov, "headline", cir["source"], cir["method"])
                break
                
        # Merge years_experience
        for cir in sorted_group:
            y = cir.get("years_experience")
            if y is not None and not profile["years_experience"]:
                # range validate
                if 0 <= y <= 60:
                    profile["years_experience"] = y
                    self._record_prov(prov, "years_experience", cir["source"], cir["method"])
                    break
                    
        # Merge skills
        skill_sources = {}
        for cir in sorted_group:
            for skill in cir.get("skills", []):
                norm_skill = normalize_skill(skill)
                if norm_skill:
                    lower_k = norm_skill.lower()
                    if lower_k not in skill_sources:
                        skill_sources[lower_k] = {
                            "name": norm_skill,
                            "sources": []
                        }
                    # Keep track of unique sources for this skill
                    if cir["source"] not in skill_sources[lower_k]["sources"]:
                        skill_sources[lower_k]["sources"].append(cir["source"])
                        self._record_prov(prov, "skills", cir["source"], cir["method"])

        for k, v in skill_sources.items():
            s_count = len(v["sources"])
            conf = min(1.0, 0.5 + 0.25 * (s_count - 1))
            profile["skills"].append({
                "name": v["name"],
                "confidence": conf
            })
            
        # Merge experience
        exp_map = {}
        for cir in sorted_group:
            for exp in cir.get("experience", []):
                c_name = exp.get("company", "") or ""
                t_name = exp.get("title", "") or ""
                key = (c_name.lower(), t_name.lower())
                
                if not c_name and not t_name:
                    continue
                    
                if key not in exp_map:
                    exp_map[key] = {
                        "company": exp.get("company"),
                        "title": exp.get("title"),
                        "start": exp.get("start"),
                        "end": exp.get("end"),
                        "summary": exp.get("summary")
                    }
                    self._record_prov(prov, "experience", cir["source"], cir["method"])
                else:
                    # fill missing
                    existing = exp_map[key]
                    if not existing["start"] and exp.get("start"):
                        existing["start"] = exp.get("start")
                        self._record_prov(prov, "experience.start", cir["source"], cir["method"])
                    if not existing["end"] and exp.get("end"):
                        existing["end"] = exp.get("end")
                        self._record_prov(prov, "experience.end", cir["source"], cir["method"])
                    if not existing["summary"] and exp.get("summary"):
                        existing["summary"] = exp.get("summary")
                        self._record_prov(prov, "experience.summary", cir["source"], cir["method"])
                        
        profile["experience"] = list(exp_map.values())
        
        # Merge education
        edu_map = {}
        for cir in sorted_group:
            for edu in cir.get("education", []):
                inst_name = edu.get("institution", "") or ""
                key = inst_name.lower()
                
                if not inst_name:
                    continue
                    
                if key not in edu_map:
                    edu_map[key] = {
                        "institution": edu.get("institution"),
                        "degree": edu.get("degree"),
                        "field": edu.get("field"),
                        "end_year": edu.get("end_year")
                    }
                    self._record_prov(prov, "education", cir["source"], cir["method"])
                else:
                    existing = edu_map[key]
                    for f in ["degree", "field", "end_year"]:
                        if not existing[f] and edu.get(f):
                            existing[f] = edu.get(f)
                            self._record_prov(prov, f"education.{f}", cir["source"], cir["method"])
                            
        profile["education"] = list(edu_map.values())
        
        # Calculate confidence score
        n_sources = len(set(c["source"] for c in sorted_group))
        score = 0.5
        score += min(0.2, 0.1 * (n_sources - 1))
        if profile["emails"]:
            score += 0.15
        if profile["phones"]:
            score += 0.05
        if len(profile["skills"]) > 3:
            score += 0.05
            
        all_nlp = all(c["method"] == "nlp_regex" for c in sorted_group)
        if all_nlp:
            score -= 0.2
            
        profile["overall_confidence"] = round(min(1.0, max(0.0, score)), 3)
        
        # Generate candidate_id
        profile["candidate_id"] = generate_candidate_id(profile.get("full_name", ""), profile.get("emails", []))
        
        return profile

    def process(self, cirs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups = self.group_cirs(cirs)
        profiles = []
        for group in groups:
            if not group:
                continue
            profiles.append(self.merge_group(group))
        return profiles
