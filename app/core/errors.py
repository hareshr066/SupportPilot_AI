import logging
from typing import Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.api_schemas import APIErrorResponse, APIErrorDetail

logger = logging.getLogger("supportpilot.api.errors")


class APIException(Exception):
    """Base API Exception with controlled error code and HTTP status code."""
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def create_error_response(code: str, message: str, status_code: int, request_id: Optional[str] = None) -> JSONResponse:
    payload = APIErrorResponse(
        error=APIErrorDetail(
            code=code,
            message=message,
            request_id=request_id
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump()
    )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning(f"APIException [{exc.code}] {exc.message} (Request ID: {request_id})")
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    # Extract first validation error message cleanly
    err_msgs = []
    for err in exc.errors():
        loc_str = " -> ".join([str(l) for l in err.get("loc", []) if l != "body"])
        msg = err.get("msg", "Invalid field")
        err_msgs.append(f"{loc_str}: {msg}" if loc_str else msg)
    
    clean_msg = "; ".join(err_msgs) if err_msgs else "Invalid request body or parameters"
    logger.warning(f"ValidationError: {clean_msg} (Request ID: {request_id})")
    
    return create_error_response(
        code="INVALID_INPUT",
        message=clean_msg,
        status_code=status.HTTP_400_BAD_REQUEST,
        request_id=request_id
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    code_map = {
        400: "INVALID_INPUT",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        503: "MODEL_UNAVAILABLE"
    }
    code = code_map.get(exc.status_code, "INTERNAL_ERROR")
    logger.warning(f"HTTPException [{exc.status_code}] {exc.detail} (Request ID: {request_id})")
    
    return create_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(f"Unhandled Exception: {exc} (Request ID: {request_id})", exc_info=True)
    
    return create_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected internal server error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id
    )
