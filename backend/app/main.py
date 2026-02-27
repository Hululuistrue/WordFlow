import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v2.router import router as v2_router
from app.core.config import Settings, get_settings
from app.db.session import init_database
from app.services.v2_job_queue import V2JobQueue


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v2_router)

    app.state.settings = settings
    app.state.v2_job_queue = V2JobQueue(settings=settings)

    @app.on_event("startup")
    async def startup() -> None:
        if settings.database_auto_create_tables:
            init_database()
        await app.state.v2_job_queue.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.v2_job_queue.stop()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
