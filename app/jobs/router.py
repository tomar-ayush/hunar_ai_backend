import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlmodel import Session, select
from pydantic import BaseModel
import uuid
import csv
import io

from app.database import get_session
from app.jobs.model import Job
from app.jobs.schema import JobCreate, JobRead, JobUpdate
from app.candidates.model import Candidate
from app.candidates.schema import CandidateCreate, CandidateRead
from app.calls.model import CallSession, Answer, Score
from app.llm.service import LLMClient
from app.people_search.service import PeopleSearchClient


router = APIRouter(prefix="/jobs", tags=["Jobs"])


class ApprovedCandidates(BaseModel):
    candidates: List[CandidateCreate]


# ──────────────────────────────────────────────
# Job CRUD (No Authentication Required)
# ──────────────────────────────────────────────

@router.post("", response_model=JobRead)
def create_job(
    job: JobCreate,
    session: Session = Depends(get_session),
):
    db_job = Job.model_validate(job)
    session.add(db_job)
    session.commit()
    session.refresh(db_job)
    return db_job


@router.get("", response_model=List[JobRead])
def get_jobs(
    session: Session = Depends(get_session),
):
    jobs = session.exec(select(Job)).all()
    return jobs


@router.get("/{id}", response_model=JobRead)
def get_job(
    id: uuid.UUID,
    session: Session = Depends(get_session),
):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{id}", response_model=JobRead)
def update_job(
    id: uuid.UUID,
    job: JobUpdate,
    session: Session = Depends(get_session),
):
    db_job = session.get(Job, id)
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")
    job_data = job.model_dump(exclude_unset=True)
    for key, value in job_data.items():
        setattr(db_job, key, value)
    session.add(db_job)
    session.commit()
    session.refresh(db_job)
    return db_job


# ──────────────────────────────────────────────
# Candidate management
# ──────────────────────────────────────────────

@router.post("/{id}/candidates", response_model=CandidateRead)
def add_candidate(
    id: uuid.UUID,
    candidate: CandidateCreate,
    session: Session = Depends(get_session),
):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_candidate = Candidate.model_validate(candidate)
    db_candidate.job_id = id
    session.add(db_candidate)
    session.commit()
    session.refresh(db_candidate)
    return db_candidate


@router.post("/{id}/candidates/csv", response_model=dict)
async def upload_candidates_csv(
    id: uuid.UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Upload candidates via CSV. Expected columns: name, phone, email"""
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    count = 0
    for row in reader:
        name = row.get("name", "").strip()
        phone = row.get("phone", "").strip()
        email = row.get("email", "").strip()
        if not name or not phone:
            continue
        candidate = Candidate(
            job_id=id,
            name=name,
            phone=phone,
            email=email,
            source="manual_upload",
            consent_status="pending",
        )
        session.add(candidate)
        count += 1

    session.commit()
    return {"status": "success", "imported": count}


@router.get("/{id}/candidates", response_model=List[CandidateRead])
def list_candidates(
    id: uuid.UUID,
    source: Optional[str] = None,
    session: Session = Depends(get_session),
):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    query = select(Candidate).where(Candidate.job_id == id)
    if source:
        query = query.where(Candidate.source == source)
    candidates = session.exec(query).all()
    return candidates


# ──────────────────────────────────────────────
# Sourcing (Apollo.IO integration)
# ──────────────────────────────────────────────

@router.post("/{id}/source")
async def source_candidates(
    id: uuid.UUID,
    session: Session = Depends(get_session),
):
    """
    1. Use LLM to extract search filters from the JD text.
    2. Query Apollo.IO People Search API with those filters.
    3. Return a preview list for user approval.
    """
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    llm_client = LLMClient()
    filters = await llm_client.extract_filters_from_jd(job.jd_text or "")

    search_client = PeopleSearchClient()
    preview_list = await search_client.search_candidates(
        title=filters.get("targetTitle", ""),
        skills=filters.get("skills", []),
        location=filters.get("location", ""),
    )

    return {"filters_used": filters, "preview": preview_list}


@router.post("/{id}/candidates/approve")
def approve_candidates(
    id: uuid.UUID,
    data: ApprovedCandidates,
    session: Session = Depends(get_session),
):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    approved = []
    for cand in data.candidates:
        db_cand = Candidate.model_validate(cand)
        db_cand.job_id = id
        db_cand.source = "people_search_api"
        session.add(db_cand)
        approved.append(db_cand)
    session.commit()

    for cand in approved:
        session.refresh(cand)

    return {"status": "success", "count": len(approved)}


# ──────────────────────────────────────────────
# Dashboard (aggregated view)
# ──────────────────────────────────────────────

@router.get("/{id}/dashboard")
def get_dashboard(
    id: uuid.UUID,
    status_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    session: Session = Depends(get_session),
):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Build candidate query with optional filters
    query = select(Candidate).where(Candidate.job_id == id)
    if source_filter:
        query = query.where(Candidate.source == source_filter)
    candidates = session.exec(query).all()

    dashboard_data = []
    for cand in candidates:
        call = session.exec(
            select(CallSession).where(CallSession.candidate_id == cand.id)
        ).first()

        answers_data = []
        score_data = None

        if call:
            if status_filter and call.status != status_filter:
                continue

            answers = session.exec(
                select(Answer).where(Answer.call_session_id == call.id)
            ).all()
            answers_data = [
                {
                    "question": a.question,
                    "extracted_answer": a.extracted_answer,
                    "confidence": a.confidence,
                }
                for a in answers
            ]

            score = session.exec(
                select(Score).where(Score.call_session_id == call.id)
            ).first()
            if score:
                score_data = {"score": score.score, "reasoning": score.reasoning}

        dashboard_data.append(
            {
                "candidate": {
                    "id": str(cand.id),
                    "name": cand.name,
                    "phone": cand.phone,
                    "email": cand.email,
                    "source": cand.source,
                    "consent_status": cand.consent_status,
                },
                "call_status": call.status if call else "not_called",
                "duration": call.duration if call else 0,
                "recording_url": call.recording_url if call else None,
                "answers": answers_data,
                "score": score_data,
            }
        )

    return {
        "job": {"id": str(job.id), "title": job.title},
        "total_candidates": len(candidates),
        "dashboard": dashboard_data,
    }
