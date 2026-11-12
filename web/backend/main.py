"""FastAPI backend for Incident Investigator web interface."""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import ulid
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from incident_investigator.investigator import Investigator
from incident_investigator.models import InvestigationEvent, InvestigationResult


@dataclass
class InvestigationRecord:
    id: str
    created_at: datetime
    status: str  # "queued", "running", "completed", "failed"
    hint: str | None
    file_names: list[str]
    result: InvestigationResult | None = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)


# In-memory storage for investigation runs
investigations: dict[str, InvestigationRecord] = {}


def _new_id(prefix: str = "inv") -> str:
    return f"{prefix}_{ulid.new().str.lower()}"


def _get_example_log_path() -> Path:
    # Resolve relative to project root
    base = Path(__file__).resolve().parent.parent.parent
    sample = base / "examples" / "db_outage.log"
    return sample


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Incident Investigator API", lifespan=lifespan)

# Allow all origins, headers, methods so Vite dev server can connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def _run_investigation(
    record: InvestigationRecord,
    file_paths: list[Path],
    cleanup: bool = False,
) -> None:
    def on_event(event: InvestigationEvent) -> None:
        data = event.model_dump(mode="json")
        record.events.append(data)
        for q in list(record.subscribers):
            q.put_nowait(data)

    try:
        record.status = "running"
        llm = getattr(app.state, "llm", None)
        investigator = Investigator(llm=llm, on_event=on_event)
        result = await investigator.investigate_async(
            files=file_paths,
            hint=record.hint,
        )
        record.result = result
        record.status = "completed"
    except Exception as exc:  # noqa: BLE001
        record.status = "failed"
        record.error = str(exc)
    finally:
        if cleanup:
            for p in file_paths:
                try:
                    p.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001, S110
                    pass
        for q in list(record.subscribers):
            q.put_nowait(None)


@app.post("/api/investigations")
async def create_investigation(
    files: list[UploadFile] = File(...),  # noqa: B008
    hint: str | None = Form(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    inv_id = _new_id()
    temp_paths: list[Path] = []
    file_names: list[str] = []

    temp_dir = tempfile.gettempdir()
    for uf in files:
        fname = uf.filename or "uploaded.log"
        file_names.append(fname)
        tmp = Path(temp_dir) / f"{inv_id}_{fname}"
        content = await uf.read()
        tmp.write_bytes(content)
        temp_paths.append(tmp)

    record = InvestigationRecord(
        id=inv_id,
        created_at=datetime.now(UTC),
        status="running",
        hint=hint,
        file_names=file_names,
    )
    investigations[inv_id] = record

    asyncio.create_task(_run_investigation(record, temp_paths, cleanup=True))

    return {"id": inv_id, "status": "running"}


@app.post("/api/investigations/sample")
async def create_sample_investigation():
    sample_path = _get_example_log_path()
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample log file not found")

    inv_id = _new_id()
    record = InvestigationRecord(
        id=inv_id,
        created_at=datetime.now(UTC),
        status="running",
        hint="Checkout failing with 504 errors",
        file_names=[sample_path.name],
    )
    investigations[inv_id] = record

    asyncio.create_task(_run_investigation(record, [sample_path], cleanup=False))

    return {"id": inv_id, "status": "running"}


@app.get("/api/investigations")
async def list_investigations():
    summaries = []
    for r in reversed(list(investigations.values())):
        summaries.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "status": r.status,
                "hint": r.hint,
                "root_cause": r.result.root_cause if r.result else None,
            }
        )
    return summaries


@app.get("/api/investigations/{investigation_id}")
async def get_investigation(investigation_id: str):
    record = investigations.get(investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return {
        "id": record.id,
        "status": record.status,
        "hint": record.hint,
        "result": record.result.model_dump(mode="json") if record.result else None,
        "error": record.error,
        "events": record.events,
    }


@app.get("/api/investigations/{investigation_id}/events")
async def stream_investigation_events(investigation_id: str, request: Request):
    record = investigations.get(investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Investigation not found")

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        record.subscribers.append(q)
        try:
            # Replay existing events
            for ev in list(record.events):
                yield {"data": json.dumps(ev)}
                if ev.get("event_type") == "REPORT_READY":
                    return

            if record.status in ("completed", "failed"):
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=0.5)
                except TimeoutError:
                    if record.status in ("completed", "failed") and q.empty():
                        break
                    continue

                if item is None:
                    break

                yield {"data": json.dumps(item)}
                if item.get("event_type") == "REPORT_READY":
                    break
        finally:
            if q in record.subscribers:
                record.subscribers.remove(q)

    return EventSourceResponse(event_generator())


@app.get("/api/investigations/{investigation_id}/report")
async def get_investigation_report(
    investigation_id: str,
    format: str = Query("md", description="Report format: md or json"),
):
    record = investigations.get(investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Investigation not found")

    if not record.result:
        raise HTTPException(
            status_code=400,
            detail=f"Investigation report not available (status: {record.status})",
        )

    if format.lower() == "json":
        return JSONResponse(content=record.result.model_dump(mode="json"))
    elif format.lower() == "md":
        return PlainTextResponse(
            content=record.result.report_markdown(),
            media_type="text/markdown",
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'md' or 'json'.")


# Mount production frontend build if present
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
