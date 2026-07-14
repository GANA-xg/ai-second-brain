import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class AppException(Exception):

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST
    ):

        self.code = code
        self.message = message
        self.status_code = status_code


class CredentialsException(AppException):
    """Raised when authentication credentials are invalid or missing."""

    def __init__(
        self,
        message: str = "Could not validate credentials",
    ):
        super().__init__(
            code="INVALID_CREDENTIALS",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


async def app_exception_handler(
    request: Request,
    exc: AppException
):

    return JSONResponse(

        status_code=exc.status_code,

        content={
            "success": False,

            "error": {

                "code": exc.code,

                "message": exc.message,

                "request_id": request.state.request_id
            }
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):

    def _sanitize(obj: object) -> object:
        """Recursively convert non-serializable objects to strings."""
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, Exception):
            return str(obj)
        return obj

    details = _sanitize(exc.errors())

    return JSONResponse(

        status_code=422,

        content={

            "success": False,

            "error": {

                "code": "VALIDATION_ERROR",

                "message": "Validation failed",

                "details": details,

                "request_id": request.state.request_id
            }
        }
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
):

    return JSONResponse(

        status_code=500,

        content={

            "success": False,

            "error": {

                "code": "INTERNAL_SERVER_ERROR",

                "message": "Something went wrong",

                "request_id": request.state.request_id
            }
        }
    )