"""Security middleware for API authentication."""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class AgencyAuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware that requires X-AGENCY-TOKEN header.

    Simulates an API Gateway authentication layer for government deployment.
    In production, this would integrate with actual IAM/OAuth systems.
    """

    # Paths that don't require authentication
    EXEMPT_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health"
    ]

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip auth for exempt paths
        if any(request.url.path.startswith(path) for path in self.EXEMPT_PATHS):
            return await call_next(request)

        # Check for required token
        token = request.headers.get("X-AGENCY-TOKEN")

        if not token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Missing X-AGENCY-TOKEN header",
                    "error_code": "MISSING_AUTH_TOKEN"
                }
            )

        if token != settings.agency_token:
            logger.warning(f"Invalid token attempt from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "Invalid authentication token",
                    "error_code": "INVALID_TOKEN"
                }
            )

        # Add user context to request state (in production, extract from JWT)
        request.state.user_id = "system"  # Mock user ID
        request.state.authenticated = True

        response = await call_next(request)
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all API requests for compliance and audit purposes.

    Critical for government deployments where all actions must be traceable.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Log request
        logger.info(
            f"API Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host,
                "user_id": getattr(request.state, "user_id", "anonymous")
            }
        )

        response = await call_next(request)

        # Log response
        logger.info(
            f"API Response: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "user_id": getattr(request.state, "user_id", "anonymous")
            }
        )

        return response
