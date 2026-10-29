import logging


def configure_logging():
    # No request bodies, cookies, credentials or SQL parameter logging.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
