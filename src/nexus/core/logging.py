from __future__ import annotations

import logging
import sys
from typing import cast

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure production structured logging.

    Application logs are emitted as JSON so they can be consumed by
    log aggregation systems without additional parsing.
    """

    level = getattr(
        logging,
        log_level.upper(),
        logging.INFO,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(
                fmt="iso",
                utc=True,
            ),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return cast(
        structlog.BoundLogger,
        structlog.get_logger(name),
    )
