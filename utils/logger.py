import logging
import os
import sys

from config import LOG_FOLDER


os.makedirs(LOG_FOLDER, exist_ok=True)

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(os.path.join(LOG_FOLDER, "scanner.log"))
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s"))
logger.addHandler(file_handler)

# Console handler (stdout) for debugging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
logger.addHandler(console_handler)
