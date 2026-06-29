"""Shared logging configuration used across the app modules."""

import logging

logger = logging.getLogger(name="autoadmin")

if not logger.handlers:
    log_formatter = logging.Formatter(
        fmt=(
            "%(levelname)s %(asctime)s (%(relativeCreated)d)- "
            "%(message)s- \t %(pathname)s F%(funcName)s L%(lineno)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(filename="logfile.log")
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(level=logging.DEBUG)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
