"""REST API around the pipeline.

Run from the project root:
    uvicorn secure_rag.api:app --reload

Flow: POST /login -> bearer token -> POST /ask. The caller's role is looked up in the user
database on every request (see security/auth.py), never taken from the request body, and
redaction is a server-side policy: clients cannot switch it off.
"""
import os
from contextlib import asynccontextmanager

import anthropic
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from secure_rag import __version__, resources
from secure_rag.ingest.indexer import build_index
from secure_rag.pipeline import ask
from secure_rag.security import auth
from secure_rag.settings import K

# Server policy. Redaction stays on unless the operator explicitly sets this to "0".
REDACT = os.getenv("SECURE_RAG_REDACT", "1") != "0"


@asynccontextmanager
async def lifespan(_app):
    auth._secret()  # fail fast if AUTH_SECRET is missing or too short
    if resources.get_collection().count() == 0:
        build_index()
    yield


app = FastAPI(title="Secure RAG API", version=__version__, lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=K, ge=1, le=10)


class Source(BaseModel):
    n: int
    doc_id: str
    title: str


class AskResponse(BaseModel):
    answer: str
    role: str
    sources: list[Source]
    invalid_citations: list[int]
    retrieved_docs: list[str]
    timings_ms: dict[str, float]


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    user = auth.verify_token(creds.credentials) if creds else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Missing, invalid, or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.get("/health")
def health():
    """Liveness only: does not load models or touch the LLM."""
    return {"status": "ok", "version": __version__}


@app.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = auth.authenticate(body.username.strip(), body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return TokenResponse(
        access_token=auth.issue_token(user), expires_in_minutes=auth.TOKEN_TTL_MINUTES
    )


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest, user: dict = Depends(current_user)):
    try:
        result = ask(body.question, k=body.k, user_role=user["role"], redact=REDACT)
    except anthropic.APIError:
        raise HTTPException(status_code=502, detail="The language model service failed.")
    # `outgoing` (the exact LLM payload) is deliberately not returned to API clients.
    return AskResponse(
        answer=result["answer"],
        role=user["role"],
        sources=result["sources"],
        invalid_citations=result["invalid_citations"],
        retrieved_docs=result["retrieved_docs"],
        timings_ms=result["timings_ms"],
    )
