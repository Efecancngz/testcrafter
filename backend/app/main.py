from fastapi import FastAPI
from app.db import Base, engine
from app.api.projects import router as projects_router
from app.api.scans import router as scans_router

Base.metadata.create_all(engine)

app = FastAPI(title="testcrafter")
app.include_router(projects_router)
app.include_router(scans_router)
