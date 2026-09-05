from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel
import uuid

from app.database import get_session
from app.auth.service import get_current_user
from app.jobs.model import Job
from app.jobs.schema import JobCreate, JobRead, JobUpdate
from app.candidates.model import Candidate
from app.candidates.schema import CandidateCreate, CandidateRead
from app.calls.model import CallSession
from app.llm.service import LLMClient
from app.people_search.service import PeopleSearchClient

router = APIRouter(prefix="/jobs", dependencies=[Depends(get_current_user)])

class ApprovedCandidates(BaseModel):
    candidates: List[CandidateCreate]

@router.post("", response_model=JobRead)
def create_job(job: JobCreate, session: Session = Depends(get_session)):
    db_job = Job.model_validate(job)
    session.add(db_job)
    session.commit()
    session.refresh(db_job)
    return db_job

@router.get("", response_model=List[JobRead])
def get_jobs(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job)).all()
    return jobs

@router.get("/{id}", response_model=JobRead)
def get_job(id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.patch("/{id}", response_model=JobRead)
def update_job(id: uuid.UUID, job: JobUpdate, session: Session = Depends(get_session)):
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

@router.post("/{id}/candidates", response_model=CandidateRead)
def add_candidate(id: uuid.UUID, candidate: CandidateCreate, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db_candidate = Candidate.model_validate(candidate)
    db_candidate.job_id = id
    session.add(db_candidate)
    session.commit()
    session.refresh(db_candidate)
    return db_candidate

@router.get("/{id}/candidates", response_model=List[CandidateRead])
def list_candidates(id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    candidates = session.exec(select(Candidate).where(Candidate.job_id == id)).all()
    return candidates

@router.post("/{id}/source")
def source_candidates(id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    llm_client = LLMClient()
    jd = job.jd_text or ""
    filters = llm_client.extract_filters_from_jd(jd)
    
    search_client = PeopleSearchClient()
    preview_list = search_client.search_candidates(
        title=filters.get("targetTitle", ""),
        skills=filters.get("skills", []),
        location=filters.get("location", "")
    )
    
    return {"preview": preview_list}

@router.post("/{id}/candidates/approve")
def approve_candidates(id: uuid.UUID, data: ApprovedCandidates, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    approved = []
    for cand in data.candidates:
        db_cand = Candidate.model_validate(cand)
        db_cand.job_id = id
        session.add(db_cand)
        approved.append(db_cand)
    session.commit()
    
    for cand in approved:
        session.refresh(cand)
        
    return {"status": "success", "count": len(approved)}

@router.get("/{id}/dashboard")
def get_dashboard(id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    candidates = session.exec(select(Candidate).where(Candidate.job_id == id)).all()
    
    dashboard_data = []
    for cand in candidates:
        session_data = session.exec(select(CallSession).where(CallSession.candidate_id == cand.id)).first()
        dashboard_data.append({
            "candidate": cand,
            "call_status": session_data.status if session_data else "Not Called",
            "answers": None,
            "score": None
        })
        
    return {"dashboard": dashboard_data}
