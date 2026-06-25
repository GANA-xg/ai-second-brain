from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.logging import LoggingMiddleware

from app.api.v1.api import api_router


setup_logging()


app = FastAPI(
    title=settings.APP_NAME
)


app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)

from fastapi.exceptions import RequestValidationError

from app.core.exceptions import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)


app.add_exception_handler(
    AppException,
    app_exception_handler
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler
)

app.add_exception_handler(
    Exception,
    generic_exception_handler
)
app.include_router(
    api_router,
    prefix=settings.API_V1_PREFIX
)