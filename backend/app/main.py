from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db import Base, engine
from app.api.projects import router as projects_router
from app.api.scans import router as scans_router
from app.api.scans import SCREENSHOTS_DIR

Base.metadata.create_all(engine)

app = FastAPI(title="testcrafter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")

app.include_router(projects_router)
app.include_router(scans_router)
