"""Health check router for infrastructure probes."""

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
async def health_check() -> None:
    """Health check endpoint for infrastructure probes."""
    return None
