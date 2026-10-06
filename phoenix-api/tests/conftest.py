"""Put the phoenix-api folder on sys.path so `from app import ...` works from the repo root."""

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
