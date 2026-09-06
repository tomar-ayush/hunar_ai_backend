import uuid
import logging
from typing import List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.jobs.model import Job
from app.candidates.model import Candidate
from app.people_search.service import PeopleSearchClient
from app.people_search.schema import (
    ScrapedCandidateRead,
    ScrapeJobResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/people-search", tags=["People Search & Scraping"]
)


@router.post("/{job_id}", response_model=ScrapeJobResponse)
async def scrape_and_save_candidates_for_job(
    job_id: uuid.UUID,
    limit: int = Query(10, description="Max candidates to scrape"),
    session: Session = Depends(get_session),
):
    """
    Pulls job details from the database by `job_id`, scrapes matching candidates
    based on the job's title, location, and required skills, and directly saves
    the new candidates into the database (`candidate` table) for this job.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dict = {
        "title": job.title,
        "target_location": job.target_location,
        "required_skills": job.required_skills or [],
        "target_seniority_level": job.target_seniority_level,
        "experience_required": job.experience_required,
        "jd_text": job.jd_text,
    }

    client = PeopleSearchClient()
    scraped_data = await client.scrape_candidates_for_job(
        job_dict, limit=limit
    )

    new_saved_candidates: List[Candidate] = []
    pairs: List[Tuple[Dict[str, Any], Candidate]] = []

    # Pre-fetch existing candidates for this job to avoid N round-trip queries
    existing_cands = session.exec(
        select(Candidate).where(Candidate.job_id == job_id)
    ).all()
    existing_by_email = {cand.email: cand for cand in existing_cands if cand.email}
    existing_by_name = {cand.name: cand for cand in existing_cands if cand.name}

    for c in scraped_data:
        name = c.get("name") or "Unknown"
        email = c.get("email") or ""
        phone = c.get("phone") or "7889440379"
        source = c.get("source") or "curated_sourcing"

        # Check in-memory maps for duplicates
        existing = existing_by_email.get(email) if email else None
        if not existing and name:
            existing = existing_by_name.get(name)

        db_cand: Candidate
        if existing:
            db_cand = existing
        else:
            db_cand = Candidate(
                job_id=job_id,
                name=name,
                phone=phone,
                email=email,
                title=c.get("title") or "",
                company=c.get("company") or "",
                location=c.get("location") or "",
                linkedin_url=c.get("linkedin_url") or "",
                profile_url=c.get("profile_url") or "",
                avatar_url=c.get("avatar_url") or "",
                skills=c.get("skills") or [],
                source=source,
                consent_status=c.get("consent_status") or "pending",
            )
            session.add(db_cand)
            new_saved_candidates.append(db_cand)
            if email:
                existing_by_email[email] = db_cand
            if name:
                existing_by_name[name] = db_cand

        pairs.append((c, db_cand))

    if new_saved_candidates:
        session.commit()
        for cand in new_saved_candidates:
            session.refresh(cand)

    response_candidates: List[ScrapedCandidateRead] = []
    for c, db_cand in pairs:
        response_candidates.append(
            ScrapedCandidateRead(
                id=db_cand.id,
                job_id=job_id,
                name=db_cand.name,
                title=c.get("title", ""),
                company=c.get("company", ""),
                location=c.get("location", ""),
                skills=c.get("skills", []),
                email=db_cand.email,
                phone=db_cand.phone,
                linkedin_url=c.get("linkedin_url", ""),
                profile_url=c.get("profile_url", ""),
                avatar_url=c.get("avatar_url", ""),
                source=db_cand.source,
                consent_status=db_cand.consent_status,
                created_at=db_cand.created_at,
            )
        )

    filters_applied = {
        "job_id": str(job.id),
        "title": job.title,
        "target_location": job.target_location,
        "required_skills": job.required_skills,
        "target_seniority_level": job.target_seniority_level,
        "experience_required": job.experience_required,
    }

    return ScrapeJobResponse(
        status="success",
        job_id=job.id,
        job_title=job.title,
        filters_applied=filters_applied,
        scraped_count=len(scraped_data),
        saved_count=len(new_saved_candidates),
        candidates=response_candidates,
    )


@router.post("/jobs/{job_id}/scrape", response_model=ScrapeJobResponse)
async def scrape_candidates_by_job_path(
    job_id: uuid.UUID,
    limit: int = Query(10, description="Max candidates to scrape"),
    session: Session = Depends(get_session),
):
    return await scrape_and_save_candidates_for_job(job_id=job_id, limit=limit, session=session)

