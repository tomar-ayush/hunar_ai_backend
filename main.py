import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.jobs.router import router as job_router
from app.candidates.router import router as candidate_router
from app.webhooks.router import router as webhooks_router
from app.agents.router import router as agent_router
from app.people_search.router import router as people_search_router


# ── Structured Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Hunar Backend starting up")
    yield
    logger.info("Hunar Backend shutting down")


# ── App ──
app = FastAPI(
    title="Hunar — AI Hiring & Reachout Portal",
    description=(
        "Unified AI Recruitment CRM. Source candidates via Apollo.IO, "
        "screen them with Hunar.AI Voice Agents, extract answers with Gemini LLM, "
        "and review results on a dashboard."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request ID Middleware ──
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        logger.info(f"[{request_id}] {request.method} {request.url.path}")
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


# ── Routers ──
app.include_router(job_router)
app.include_router(candidate_router)
app.include_router(webhooks_router)
app.include_router(agent_router)
app.include_router(people_search_router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "hunar-backend", "version": "1.0.0"}
