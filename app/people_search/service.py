import httpx
import logging
from typing import List, Dict, Any, Optional

from app.config import settings
from app.people_search.mock_data import get_mock_candidates_for_job

logger = logging.getLogger(__name__)


class PeopleSearchClient:
    """
    People Search & Candidate Sourcing client.

    Capabilities:
    1. Apollo.IO People Search (when valid paid plan key is configured).
    2. Curated Indian tech candidate pool (30 candidates with phone 7889440379)
       as fallback when Apollo is unavailable for demo purposes.
    """

    def __init__(self):
        self.base_url = settings.APOLLO_BASE_URL
        self.api_key = settings.APOLLO_API_KEY
        self.timeout = 30
        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key or "",
        }

    async def scrape_candidates_for_job(
        self, job_data: Dict[str, Any], limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Scrape/source candidates matching a job specification.
        """
        title = job_data.get("title") or ""
        skills = job_data.get("required_skills") or []
        location = job_data.get("target_location") or ""
        seniority = job_data.get("target_seniority_level") or ""

        return await self.search_candidates(
            title=title,
            skills=skills,
            location=location,
            seniority=seniority,
            limit=limit,
        )

    async def search_candidates(
        self,
        title: str,
        skills: List[str],
        location: str,
        seniority: str = "",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Search for candidates matching the given parameters.
        Tries Apollo.IO first if an API key is available.
        Falls back to curated Indian candidate dataset with phone 7889440379.
        """
        # 1. Try Apollo.IO if key is provided
        if self.api_key:
            try:
                apollo_results = await self._search_apollo(
                    title=title,
                    skills=skills,
                    location=location,
                    limit=limit,
                )
                if apollo_results:
                    return apollo_results
            except Exception as e:
                logger.warning(
                    f"Apollo API search failed ({e}). Using curated Indian candidate dataset fallback."
                )

        # 2. Fallback: Curated Indian Candidate Profiles (phone 7889440379)
        return get_mock_candidates_for_job(
            skills=skills, location=location, title=title, limit=limit
        )

    async def _search_apollo(
        self,
        title: str,
        skills: List[str],
        location: str,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Query Apollo.IO mixed_people search."""
        payload = {
            "api_key": self.api_key,
            "q_keywords": ", ".join(skills) if skills else title,
            "person_titles": [title] if title else [],
            "person_locations": [location] if location else [],
            "page": 1,
            "per_page": limit,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/mixed_people/search",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            people = data.get("people", [])
            results = []
            for person in people:
                org = person.get("organization") or {}
                loc_parts = [
                    p
                    for p in [
                        person.get("city"),
                        person.get("state"),
                        person.get("country"),
                    ]
                    if p
                ]
                results.append(
                    {
                        "name": person.get("name")
                        or f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                        "title": person.get("title", "") or title,
                        "company": org.get("name", ""),
                        "location": ", ".join(loc_parts) or location,
                        "skills": skills,
                        "email": person.get("email", ""),
                        "phone": "7889440379",
                        "linkedin_url": person.get("linkedin_url", ""),
                        "profile_url": person.get("linkedin_url", ""),
                        "avatar_url": person.get("photo_url", ""),
                        "source": "apollo",
                        "consent_status": "pending",
                    }
                )
            return results

    async def enrich_person(
        self, first_name: str, last_name: str, company: str
    ) -> Dict[str, Any]:
        """Enrich a single person via Apollo.IO to get contact details."""
        if not self.api_key:
            return {
                "email": "",
                "phone": "7889440379",
                "linkedin_url": "",
                "title": "",
                "company": company,
            }

        payload = {
            "api_key": self.api_key,
            "first_name": first_name,
            "last_name": last_name,
            "organization_name": company,
            "reveal_personal_emails": True,
            "reveal_phone_number": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/people/match",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                person = data.get("person", {})

                return {
                    "email": person.get("email", ""),
                    "phone": "7889440379",
                    "linkedin_url": person.get("linkedin_url", ""),
                    "title": person.get("title", ""),
                    "company": (
                        person.get("organization", {}).get("name", "")
                        if person.get("organization")
                        else company
                    ),
                }

            except Exception as e:
                logger.error(f"Enrichment error: {e}")
                return {
                    "email": "",
                    "phone": "7889440379",
                    "linkedin_url": "",
                    "title": "",
                    "company": company,
                }
