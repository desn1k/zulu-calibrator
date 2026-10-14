import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
def healthz(request: Request) -> JSONResponse:
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("health check: database unavailable")
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})
