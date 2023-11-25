"""config.py

This module contains pairbot's configuration settings, stored as module-level variables
with uppercase names.
"""

import os
from pathlib import Path
from datetime import time
import logging.config

import dotenv
import discord

BASE_DIR = Path(__file__).resolve().parent.parent

class ConfigError(Exception):
    """Exception raised for errors in application configuration."""
    pass

ENV = os.environ.get("ENV", "development")
if ENV not in ["development", "testing", "production"]:
    raise ConfigError(f"Invalid environment: {ENV}")

DOTENV_PATH = os.path.join(BASE_DIR, f".env.{ENV}")
if not os.path.isfile(DOTENV_PATH):
    raise ConfigError(f"Could not find dotenv file {DOTENV_PATH}.")
dotenv.load_dotenv(DOTENV_PATH)

# Load required environment variables
try:
    DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
    DATABASE_URL = os.environ["DATABASE_URL"]
    PAIRING_TIME = time.fromisoformat(os.environ["PAIRING_TIME"])
except KeyError as e:
    raise ConfigError(f"Missing environment variable: {e.args[0]}.")

# Configure logger
LOGGING = {
    "version": 1,
    "formatters": {
        "default": {
            "format": "%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
            "datefmt": "%H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    }
}

logging.config.dictConfig(LOGGING)

logger = logging.getLogger(__name__)

# Log config information
logger.info(f"Running in {ENV} mode.")

# Disable PyNaCl warning
discord.VoiceClient.warn_nacl = False
