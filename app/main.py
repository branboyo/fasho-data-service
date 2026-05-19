from fastapi import FastAPI

from app.api.jobs import router as jobs_router


def create_app() -> FastAPI:
    app = FastAPI(title="Fasho Data Service", version="0.1.0")
    app.include_router(jobs_router, prefix="/api/v1")
    return app


app = create_app()
