"""HTTP API. Run with: uvicorn eventflow_ingest.api:app"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .auth import AuthError, authenticate
from .config import Settings, load_settings
from .db import apply_migrations, create_pool
from .validation import Rejected, RequestError, validate_batch

MAX_BODY_BYTES = 5 * 1024 * 1024  # ~10 KB per event x 500 events


@cache
def get_settings() -> Settings:
    return load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: open the DB pool and apply migrations. Shutdown: close the pool."""
    settings = get_settings()
    app.state.pool = await create_pool(settings.database_url)
    await apply_migrations(app.state.pool)
    yield
    await app.state.pool.close()


app = FastAPI(title="EventFlow ingest", version="0.1.0", lifespan=lifespan)


def error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}, **extra})


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness: the process is up. Says nothing about the database."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request):
    """Readiness: the database answers. Load balancers route traffic only to ready instances."""
    try:
        await request.app.state.pool.fetchval("SELECT 1")
    except Exception:
        return error(503, "not_ready", "database unavailable")
    return {"status": "ready"}


@app.post("/v1/events:batch")
async def ingest_batch(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
):
    # 1. Who is calling? Each token may write as exactly one source_id.
    try:
        source_id = authenticate(authorization, settings.agent_tokens)
    except AuthError as exc:
        return error(401, "unauthorized", str(exc))

    # 2. Is the body a reasonable size and valid JSON?
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return error(413, "too_large", f"body exceeds {MAX_BODY_BYTES} bytes")
    try:
        decoded = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error(400, "bad_request", "body is not valid UTF-8 JSON")

    # 3. Validate: identity problems fail the request; content problems reject single events.
    try:
        results = validate_batch(decoded, source_id, settings.max_batch_events)
    except RequestError as exc:
        code = "unauthorized" if exc.status == 401 else "bad_request"
        return error(exc.status, code, exc.message)

    # 4. Storage arrives on Day 3. Until then, never return 200: per the contract,
    #    200 means "committed to the database".
    rejected = sum(isinstance(r, Rejected) for r in results)
    return error(
        501,
        "not_implemented",
        "validation passed; storage is not implemented yet",
        validated={"valid": len(results) - rejected, "rejected": rejected},
    )
