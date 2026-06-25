import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("app")


class LoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        start_time = time.time()

        response = await call_next(request)

        process_time = round(time.time() - start_time, 4)

        logger.info(
            f"{request.method} "
            f"{request.url.path} "
            f"status={response.status_code} "
            f"latency={process_time}s "
            f"request_id={request.state.request_id}"
        )

        return response