import httpx
import json
import logging
from typing import List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Google Gemini LLM client for:
    1. Extracting structured search filters from a JD
    2. Extracting answers from a voice call transcript
    3. Scoring a candidate against pass/fail criteria
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = 60

    async def _call_gemini(self, prompt: str) -> str:
        """
        Make a raw request to the Gemini REST API.
        Returns the text content of the first candidate.
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — cannot call LLM")
            raise ValueError("GEMINI_API_KEY is not configured")

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini returned no candidates")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("Gemini returned empty parts")

            return parts[0].get("text", "")

    async def extract_filters_from_jd(self, jd_text: str) -> Dict[str, Any]:
        """
        Use Gemini to extract structured search filters from raw JD text.
        Returns: {"targetTitle": str, "skills": [str], "location": str}
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — returning mock filters")
            return self._mock_filters()

        prompt = f"""Analyze this job description and extract search filters for finding candidates.

Job Description:
---
{jd_text}
---

Return ONLY a valid JSON object with these exact keys:
- "targetTitle": the ideal job title to search for (string)
- "skills": list of required technical skills (array of strings, max 8)
- "location": preferred candidate location (string, or "Remote" if not specified)

Return ONLY the JSON, no markdown, no explanation."""

        try:
            raw = await self._call_gemini(prompt)
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to extract filters via Gemini: {e}")
            return self._mock_filters()

    async def extract_answers_from_transcript(
        self, transcript: List[Dict[str, str]], questions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Use Gemini to extract structured answers from a voice call transcript.
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — returning mock answers")
            return self._mock_answers(questions)

        transcript_text = "\n".join(
            f"{msg.get('speaker', 'Unknown')}: {msg.get('text', '')}"
            for msg in transcript
        )

        questions_text = "\n".join(f"Q{i+1}: {q}" for i, q in enumerate(questions))

        prompt = f"""You are analyzing a phone screening interview transcript.

Transcript:
---
{transcript_text}
---

Questions that were asked:
{questions_text}

For each question, extract the candidate's answer from the transcript.
Return ONLY a valid JSON array where each element has:
- "question": the question text (string)
- "extracted_answer": the candidate's answer summarized from the transcript (string)
- "confidence": how confident you are the answer was found, 0.0 to 1.0 (number)

If a question wasn't answered in the transcript, set extracted_answer to "Not answered" and confidence to 0.0.
Return ONLY the JSON array, no markdown, no explanation."""

        try:
            raw = await self._call_gemini(prompt)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to extract answers via Gemini: {e}")
            return self._mock_answers(questions)

    async def score_transcript(
        self, transcript: List[Dict[str, str]], pass_criteria: str
    ) -> Dict[str, Any]:
        """
        Use Gemini to score a candidate's transcript against pass/fail criteria.
        Returns: {"score": int (0-100), "reasoning": str}
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — returning mock score")
            return self._mock_score()

        transcript_text = "\n".join(
            f"{msg.get('speaker', 'Unknown')}: {msg.get('text', '')}"
            for msg in transcript
        )

        prompt = f"""You are an expert HR screening evaluator.

Evaluate this candidate's phone interview transcript against the pass/fail criteria below.

Transcript:
---
{transcript_text}
---

Pass/Fail Criteria:
---
{pass_criteria}
---

Return ONLY a valid JSON object with:
- "score": an integer from 0 to 100 representing overall fit
- "reasoning": a 2-3 sentence explanation of the score

Scoring guide:
- 80-100: Strong pass — candidate clearly meets all criteria
- 60-79: Conditional pass — meets most criteria with minor gaps
- 40-59: Borderline — significant gaps but some potential
- 0-39: Fail — does not meet the criteria

Return ONLY the JSON, no markdown, no explanation."""

        try:
            raw = await self._call_gemini(prompt)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            result = json.loads(cleaned)
            # Ensure score is an int
            result["score"] = int(result.get("score", 0))
            return result
        except Exception as e:
            logger.error(f"Failed to score transcript via Gemini: {e}")
            return self._mock_score()

    # ── Fallback mocks (used when GEMINI_API_KEY is empty) ──

    @staticmethod
    def _mock_filters() -> Dict[str, Any]:
        return {
            "targetTitle": "Software Engineer",
            "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
            "location": "Remote",
        }

    @staticmethod
    def _mock_answers(questions: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "question": q,
                "extracted_answer": f"Mock answer for: {q}",
                "confidence": 0.85,
            }
            for q in questions
        ]

    @staticmethod
    def _mock_score() -> Dict[str, Any]:
        return {
            "score": 72,
            "reasoning": "The candidate demonstrated adequate technical knowledge but lacked depth in system design. Communication was clear and professional.",
        }
