from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.logging import LoggingMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router


setup_logging(level=settings.AUTH_LOG_LEVEL)


app = FastAPI(
    title=settings.APP_NAME
)
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",

]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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