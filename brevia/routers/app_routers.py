"""Add brevia app routers."""
from fastapi import FastAPI
from brevia import index
from brevia.routers import (
    analyze_router,
    index_router,
    collections_router,
    chat_history_router,
    audio_router,
    jobs_router,
    qa_router,
    status_router,
    completion_router
)


def add_routers(app: FastAPI) -> None:
    """Add brevia APP routers to FastAPI instance"""
    app.include_router(index_router.router)
    app.include_router(analyze_router.router)
    app.include_router(collections_router.router)
    app.include_router(audio_router.router)
    app.include_router(jobs_router.router)
    app.include_router(chat_history_router.router)
    app.include_router(qa_router.router)
    app.include_router(status_router.router)
    app.include_router(completion_router.router)

    index.init_index()
