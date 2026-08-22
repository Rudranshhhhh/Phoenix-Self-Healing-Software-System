"""
Phoenix Backend — MongoDB Client

Wraps pymongo to provide typed collection accessors.
One global client instance per process — thread-safe by design.
"""
from __future__ import annotations

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def init_db(mongo_uri: str, db_name: str) -> None:
    """Initialise the global MongoDB connection."""
    global _client, _db
    _client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        socketTimeoutMS=10_000,
    )
    _db = _client[db_name]

    # Verify connection
    _client.admin.command("ping")
    logger.info("MongoDB: connected to database '%s'", db_name)

    # Create indexes
    _create_indexes()


def _create_indexes() -> None:
    """Create MongoDB indexes for common query patterns."""
    db = get_db()

    # incidents — query by service, status, severity, detected_at
    db["incidents"].create_index([("service", 1), ("detected_at", -1)])
    db["incidents"].create_index([("status", 1)])
    db["incidents"].create_index([("severity", 1)])
    db["incidents"].create_index([("incident_id", 1)], unique=True)
    db["incidents"].create_index([("resolved", 1)])

    # metrics — query by service and timestamp range
    db["metrics"].create_index([("service", 1), ("timestamp", -1)])
    db["metrics"].create_index([("timestamp", -1)])

    # recovery_logs — query by incident_id
    db["recovery_logs"].create_index([("incident_id", 1)])

    # system_events — query by event_type and timestamp
    db["system_events"].create_index([("event_type", 1), ("timestamp", -1)])

    logger.info("MongoDB: indexes created")


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("MongoDB not initialised. Call init_db() first.")
    return _db


def get_collection(name: str) -> Collection:
    return get_db()[name]


# Typed collection accessors
def incidents() -> Collection:
    return get_collection("incidents")


def metrics() -> Collection:
    return get_collection("metrics")


def recovery_logs() -> Collection:
    return get_collection("recovery_logs")


def system_events() -> Collection:
    return get_collection("system_events")


def settings_col() -> Collection:
    return get_collection("settings")
