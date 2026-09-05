import httpx
import logging
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class PeopleSearchClient:
    """
    Real Apollo.IO People Search API client.

    Uses two endpoints:
    - POST /mixed_people/search  → find candidates by title, location, keywords
    - POST /people/match         → enrich a single person (get email + phone)

    Docs: https://apolloio.github.io/apollo-api-docs/
    """

    def __init__(self):
        self.base_url = settings.APOLLO_BASE_URL
        self.api_key = settings.APOLLO_API_KEY
        self.timeout = 30
        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    async def search_candidates(
        self, title: str, skills: List[str], location: str, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search Apollo.IO for people matching the given filters.
        Returns a preview list of candidates with name, title, company, LinkedIn.
        """
        if not self.api_key:
            logger.warning("APOLLO_API_KEY not set — returning mock data")
            return self._mock_search(title, location)

        payload = {
            "api_key": self.api_key,
            "q_keywords": ", ".join(skills) if skills else title,
            "person_titles": [title] if title else [],
            "person_locations": [location] if location else [],
            "page": 1,
            "per_page": per_page,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
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
                    results.append({
                        "apollo_id": person.get("id"),
                        "name": person.get("name", ""),
                        "first_name": person.get("first_name", ""),
                        "last_name": person.get("last_name", ""),
                        "title": person.get("title", ""),
                        "company": person.get("organization", {}).get("name", "") if person.get("organization") else "",
                        "location": person.get("city", "") + (", " + person.get("state", "") if person.get("state") else ""),
                        "linkedin_url": person.get("linkedin_url", ""),
                        "email": person.get("email", ""),
                        "phone": "",  # Phone requires enrichment
                    })
                return results

            except httpx.HTTPStatusError as e:
                logger.error(f"Apollo API error {e.response.status_code}: {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Apollo HTTP error: {e}")
                raise

    async def enrich_person(self, first_name: str, last_name: str, company: str) -> Dict[str, Any]:
        """
        Enrich a single person via Apollo.IO to get email + phone.
        Uses the /people/match endpoint.
        """
        if not self.api_key:
            logger.warning("APOLLO_API_KEY not set — returning mock enrichment")
            return {"email": f"{first_name.lower()}@example.com", "phone": "+1-555-0100"}

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
                    "phone": (person.get("phone_numbers", [{}]) or [{}])[0].get("sanitized_number", ""),
                    "linkedin_url": person.get("linkedin_url", ""),
                    "title": person.get("title", ""),
                    "company": person.get("organization", {}).get("name", "") if person.get("organization") else "",
                }

            except httpx.HTTPError as e:
                logger.error(f"Apollo enrichment error: {e}")
                raise

    @staticmethod
    def _mock_search(title: str, location: str) -> List[Dict[str, Any]]:
        """Fallback mock data when no API key is configured."""
        return [
            {
                "apollo_id": "mock-001",
                "name": "Priya Sharma",
                "first_name": "Priya",
                "last_name": "Sharma",
                "title": title or "Software Engineer",
                "company": "Razorpay",
                "location": location or "Bangalore, IN",
                "linkedin_url": "https://linkedin.com/in/priyasharma",
                "email": "priya.sharma@razorpay.com",
                "phone": "+91-9876543210",
            },
            {
                "apollo_id": "mock-002",
                "name": "Arjun Mehta",
                "first_name": "Arjun",
                "last_name": "Mehta",
                "title": title or "Software Engineer",
                "company": "Flipkart",
                "location": location or "Bangalore, IN",
                "linkedin_url": "https://linkedin.com/in/arjunmehta",
                "email": "arjun.mehta@flipkart.com",
                "phone": "+91-9123456789",
            },
        ]
