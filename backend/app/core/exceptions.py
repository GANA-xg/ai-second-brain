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

    return JSONResponse(

        status_code=422,

        content={

            "success": False,

            "error": {

                "code": "VALIDATION_ERROR",

                "message": "Validation failed",

                "details": exc.errors(),

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