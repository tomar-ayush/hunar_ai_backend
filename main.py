from fastapi import FastAPI
import uvicorn

from app.auth.router import router as auth_router
from app.jobs.router import router as job_router
from app.candidates.router import router as candidate_router
from app.webhooks.router import router as webhooks_router

app = FastAPI(title="Hunar Backend API")

app.include_router(auth_router)
app.include_router(job_router)
app.include_router(candidate_router)
app.include_router(webhooks_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "hunar-backend"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
