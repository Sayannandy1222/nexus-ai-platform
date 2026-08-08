from fastapi import FastAPI

from nexus.api.router import api_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="NEXUS AI Platform",
        description=(
            "Production-grade AI context, RAG, Redis/Valkey observability and LLMOps platform."
        ),
        version="0.1.0",
    )

    application.include_router(api_router)

    return application


app = create_app()
