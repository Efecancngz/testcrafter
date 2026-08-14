from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.scans import router as scans_router

app = FastAPI(title="testcrafter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(scans_router)


@app.on_event("startup")
def _fail_interrupted_runs() -> None:
    # Any Run left at pending/running means the backend process was killed
    # or restarted mid-execution (this project runs without --reload, so
    # devs restart the process after backend code changes — see
    # HANDOFF.md/CONTRIBUTING.md). Without this, the 409 "already in
    # progress" guard in run_scan would lock the scan forever with no way
    # to unstick it short of manual DB surgery.
    from datetime import datetime, timezone
    from app.db import SessionLocal
    from app.models import Run

    session = SessionLocal()
    try:
        interrupted = session.query(Run).filter(Run.status.in_(["pending", "running"])).all()
        for run in interrupted:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
        if interrupted:
            session.commit()
    finally:
        session.close()
