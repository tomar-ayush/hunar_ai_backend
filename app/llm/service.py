from typing import List, Dict, Any

class LLMClient:
    def __init__(self):
        pass

    async def extract_filters_from_jd(self, jd_text: str) -> Dict[str, Any]:
        """
        Extract structured filters from a raw Job Description text.
        """
        # Mock implementation
        return {
            "targetTitle": "Software Engineer",
            "skills": ["Python", "FastAPI", "SQLModel"],
            "location": "San Francisco, CA"
        }

    async def extract_answers_from_transcript(self, transcript: List[Dict[str, str]], questions: List[str]) -> List[Dict[str, Any]]:
        """
        Extract answers to specific questions based on the call transcript.
        """
        # Mock implementation
        results = []
        for q in questions:
            results.append({
                "question": q,
                "extracted_answer": f"Mock answer for: {q}",
                "confidence": 0.95
            })
        return results

    async def score_transcript(self, transcript: List[Dict[str, str]], pass_criteria: str) -> Dict[str, Any]:
        """
        Score the overall transcript against the pass criteria.
        """
        # Mock implementation
        return {
            "score": 85,
            "reasoning": "The candidate demonstrated strong knowledge of the required skills but lacked some depth in system design."
        }
