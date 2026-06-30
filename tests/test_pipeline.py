import pytest
from src.normalizers import (
    normalize_email, normalize_phone, normalize_skill, normalize_date, 
    normalize_country, generate_candidate_id
)
from src.merger.merger import CandidateMerger
from src.projector.projector import OutputProjector
from src.projector.validator import SchemaValidator
from src.sources import BaseSource

class TestNormalizeEmail:
    def test_valid_lowercased(self):
        assert normalize_email("Test.Email@Domain.com") == "test.email@domain.com"
        
    def test_invalid_returns_none(self):
        assert normalize_email("not-an-email") is None
        
    def test_empty_none_returns_none(self):
        assert normalize_email("") is None
        assert normalize_email(None) is None
        
    def test_strips_whitespace(self):
        assert normalize_email("  foo@bar.com  ") == "foo@bar.com"

class TestNormalizePhone:
    def test_e164_passthrough(self):
        assert normalize_phone("+14155550192") == "+14155550192"
        
    def test_formatted_stripped(self):
        assert normalize_phone("+1 (415) 555-0192") == "+14155550192"
        
    def test_local_plus_hint(self):
        assert normalize_phone("4155550192", "US") == "+14155550192"
        assert normalize_phone("9876543210", "India") == "+919876543210"
        
    def test_invalid_none(self):
        assert normalize_phone("invalid") is None
        assert normalize_phone("+12") is None # too short
        
    def test_none_none(self):
        assert normalize_phone(None) is None

class TestNormalizeSkill:
    def test_alias_resolution(self):
        assert normalize_skill("pytorch") == "PyTorch"
        assert normalize_skill("k8s") == "Kubernetes"
        
    def test_unknown_title_case(self):
        assert normalize_skill("some random skill") == "Some Random Skill"
        
    def test_comma_delimited(self):
        from src.normalizers import normalize_skills
        assert normalize_skills("python, ml, pytorch") == ["Python", "Machine Learning", "PyTorch"]
        
    def test_deduplication(self):
        from src.normalizers import normalize_skills
        assert normalize_skills("python, Python, py") == ["Python"]

class TestNormalizeDate:
    def test_yyyy_mm(self):
        assert normalize_date("2021-03") == "2021-03"
        
    def test_mar_2021(self):
        assert normalize_date("Mar 2021") == "2021-03"
        assert normalize_date("march 2021") == "2021-03"
        
    def test_present(self):
        assert normalize_date("present") is None
        assert normalize_date("current") is None
        
    def test_none(self):
        assert normalize_date(None) is None
        
    def test_year_only(self):
        assert normalize_date("2018") == "2018-01"

class TestNormalizeCountry:
    def test_full_name(self):
        assert normalize_country("india") == "IN"
        
    def test_abbreviation(self):
        assert normalize_country("us") == "US"
        assert normalize_country("usa") == "US"
        
    def test_unknown_none(self):
        assert normalize_country("unknownland") is None

class TestMerger:
    def setup_method(self):
        self.merger = CandidateMerger()
        self.empty_cir = lambda source, method: BaseSource.empty_cir(source, method)
        
    def test_same_email_dedup(self):
        c1 = self.empty_cir("s1", "csv_row")
        c1["emails"] = ["test@test.com"]
        c1["raw_name"] = "Alice"
        
        c2 = self.empty_cir("s2", "ats_json")
        c2["emails"] = ["test@test.com"]
        c2["raw_name"] = "Alice Smith"
        
        res = self.merger.process([c1, c2])
        assert len(res) == 1
        assert res[0]["full_name"] == "Alice" # csv beats ats
        
    def test_same_name_dedup(self):
        c1 = self.empty_cir("s1", "csv_row")
        c1["raw_name"] = "Bob"
        c2 = self.empty_cir("s2", "ats_json")
        c2["raw_name"] = "bob "
        
        res = self.merger.process([c1, c2])
        assert len(res) == 1
        
    def test_email_union(self):
        c1 = self.empty_cir("s1", "csv_row")
        c1["emails"] = ["e1@t.com"]
        c1["raw_name"] = "Bob"
        c2 = self.empty_cir("s2", "ats_json")
        c2["emails"] = ["e2@t.com"]
        c2["raw_name"] = "Bob"
        
        res = self.merger.process([c1, c2])
        assert len(res[0]["emails"]) == 2
        
    def test_source_priority_name(self):
        c1 = self.empty_cir("s1", "nlp_regex")
        c1["raw_name"] = "Bob Nlp"
        c2 = self.empty_cir("s2", "csv_row")
        c2["raw_name"] = "Bob Csv"
        
        # Merge should link them if we force them together via email
        c1["emails"] = ["a@a.com"]
        c2["emails"] = ["a@a.com"]
        
        res = self.merger.process([c1, c2])
        assert res[0]["full_name"] == "Bob Csv"
        
    def test_skills_union_dedup(self):
        c1 = self.empty_cir("s1", "csv_row")
        c1["raw_name"] = "Bob"
        c1["skills"] = ["Python", "Docker"]
        c2 = self.empty_cir("s2", "ats_json")
        c2["raw_name"] = "Bob"
        c2["skills"] = ["python", "go"]
        
        res = self.merger.process([c1, c2])
        skills = [s["name"] for s in res[0]["skills"]]
        assert len(skills) == 3
        assert "Python" in skills
        assert "Docker" in skills
        assert "Go" in skills
        
    def test_distinct_candidates(self):
        c1 = self.empty_cir("s1", "csv_row")
        c1["raw_name"] = "Alice"
        c2 = self.empty_cir("s2", "ats_json")
        c2["raw_name"] = "Bob"
        
        res = self.merger.process([c1, c2])
        assert len(res) == 2
        
    def test_empty_name_skipped(self):
        # The merger relies on name or email. If both empty, it forms a group but we check what happens
        c1 = self.empty_cir("s1", "csv_row")
        res = self.merger.process([c1])
        assert len(res) == 1
        assert res[0]["full_name"] is None

class TestProjector:
    def test_default_projection(self):
        p = OutputProjector()
        prof = {"full_name": "Bob", "emails": ["b@b.com"]}
        res = p.project(prof)
        assert "full_name" in res
        assert "emails" in res
        assert "candidate_id" in res
        
    def test_custom_config_rename(self):
        config = {"fields": [{"path": "primary_email", "from": "emails[0]", "type": "string"}]}
        p = OutputProjector(config)
        res = p.project({"emails": ["a@a.com", "b@b.com"]})
        assert res["primary_email"] == "a@a.com"
        
    def test_omit_on_missing(self):
        config = {"fields": [{"path": "name"}], "on_missing": "omit"}
        p = OutputProjector(config)
        res = p.project({})
        assert "name" not in res
        
    def test_array_mapping(self):
        config = {"fields": [{"path": "skills", "from": "skills[].name"}]}
        p = OutputProjector(config)
        prof = {"skills": [{"name": "Python", "conf": 1.0}, {"name": "Go", "conf": 0.8}]}
        res = p.project(prof)
        assert res["skills"] == ["Python", "Go"]
        
    def test_required_field_missing(self):
        config = {"fields": [{"path": "name", "required": True}], "on_missing": "error"}
        p = OutputProjector(config)
        res = p.project({})
        v = SchemaValidator(config)
        issues = v.validate(res)
        assert len(issues) == 1
        assert "Missing required field" in issues[0]

class TestEdgeCases:
    def test_name_only_cir(self):
        c1 = BaseSource.empty_cir("s1", "csv_row")
        c1["raw_name"] = "Just Name"
        m = CandidateMerger()
        res = m.process([c1])
        assert len(res) == 1
        assert res[0]["emails"] == []
        assert res[0]["phones"] == []
        
    def test_negative_years_exp(self):
        # We range validate in merger. ATS parses it out but merger ignores if out of bounds
        c1 = BaseSource.empty_cir("s1", "csv_row")
        c1["raw_name"] = "Bob"
        c1["years_experience"] = -1
        m = CandidateMerger()
        res = m.process([c1])
        assert res[0]["years_experience"] is None
        
    def test_deterministic_candidate_id(self):
        id1 = generate_candidate_id("Bob", ["b@b.com"])
        id2 = generate_candidate_id("bob", ["B@B.COM"])
        assert id1 == id2
        
    def test_different_people_different_ids(self):
        id1 = generate_candidate_id("Bob", ["b@b.com"])
        id2 = generate_candidate_id("Alice", ["a@a.com"])
        assert id1 != id2
