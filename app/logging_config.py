import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)

    formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
