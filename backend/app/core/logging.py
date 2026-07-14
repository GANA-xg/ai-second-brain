"""
Structured logging setup using structlog.

Produces JSON-formatted logs for production observability.
Integrates with Python's standard logging for backward compatibility.
"""

import logging
import structlog


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Uses structlog to produce JSON-formatted log entries.
    Python stdlib loggers are chained through structlog processors
    so existing logger.getLogger() calls continue to work.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure root logger so all stdlib loggers are captured
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        force=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger by name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        A structlog BoundLogger that outputs JSON.
    """
    return structlog.get_logger(name)
