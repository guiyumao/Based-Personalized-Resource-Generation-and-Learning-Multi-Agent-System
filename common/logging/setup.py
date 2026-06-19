"""Centralized logging configuration."""

import logging


def configure_logging(service_name: str) -> None:
    """Apply a simple structured logging format for all services."""

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s | {service_name} | %(levelname)s | %(name)s | %(message)s",
    )
