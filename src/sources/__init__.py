from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseSource(ABC):
    @abstractmethod
    def extract(self) -> List[Dict[str, Any]]:
        pass

    @staticmethod
    def empty_cir(source: str, method: str) -> Dict[str, Any]:
        """
        Creates an empty Canonical Intermediate Record (CIR).
        """
        return {
            "source": source,
            "method": method,
            "raw_name": None,
            "emails": [],
            "phones": [],
            "links": {
                "linkedin": None,
                "github": None,
                "portfolio": None,
                "other": []
            },
            "location": {"city": None, "region": None, "country": None},
            "headline": None,
            "years_experience": None,
            "skills": [],
            "experience": [],
            "education": []
        }
