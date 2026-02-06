import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s", # "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    handlers=[logging.FileHandler("app.log", mode="a"), logging.StreamHandler()],
)
