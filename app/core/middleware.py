import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("supportpilot.api.middleware")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware injecting unique request_id into request state & headers,
    measuring latency, and logging structured request telemetry.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        t0 = time.time()
        
        # 1. Generate or extract Request ID
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        
        # 2. Process Request
        response = await call_next(request)
        
        # 3. Calculate Latency & Inject Headers
        latency_ms = round((time.time() - t0) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        
        # 4. Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if "Server" in response.headers:
            del response.headers["Server"]
            
        # 5. Log Request Summary (excluding bodies & tokens)
        logger.info(
            f"[{request.method}] {request.url.path} -> {response.status_code} "
            f"({latency_ms}ms) [RequestID: {request_id}]"
        )
        
        return response
