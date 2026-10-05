"""
Phoenix API — Database

MongoDB connection and initialization.
Declares schema/indexes.
"""
import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from .config import config

logger = logging.getLogger(__name__)

# Global client (initialized on app startup)
_client: Optional[MongoClient] = None


def get_database():
    """Return the MongoDB database instance."""
    global _client
    if _client is None:
        raise RuntimeError("Database not initialized. Call init_database() on app startup.")
    return _client[config.MONGO_DB_NAME]


def init_database() -> bool:
    """
    Initialize the MongoDB connection.
    Create necessary collections and indexes.
    Return True on success, False on failure.
    """
    global _client
    try:
        _client = MongoClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
        )
        # Verify connection
        _client.admin.command("ping")
        logger.info("✓ MongoDB connected")

        db = _client[config.MONGO_DB_NAME]

        # Create collections and indexes
        _create_collections_and_indexes(db)

        return True

    except ServerSelectionTimeoutError as exc:
        logger.error("✗ MongoDB connection failed: %s", exc)
        return False
    except Exception as exc:
        logger.error("✗ Database initialization failed: %s", exc)
        return False


def _create_collections_and_indexes(db):
    """Create collections and indexes if they don't exist."""

    # Counters collection for INC-001 style IDs
    if "counters" not in db.list_collection_names():
        db.create_collection("counters")
        db.counters.insert_one({"_id": "incident_seq", "seq": 0})
        logger.info("✓ Created counters collection")

    # Incidents collection
    if "incidents" not in db.list_collection_names():
        db.create_collection("incidents")
    db.incidents.create_index("incident_id", unique=True)
    db.incidents.create_index("source")
    db.incidents.create_index("status")
    db.incidents.create_index([(("created_at", -1))])
    # Deduplication index: (repository, commit, run_id)
    db.incidents.create_index(
        [("repository", 1), ("commit", 1), ("run_id", 1)],
        sparse=True,  # sparse because Docker incidents may not have run_id
    )
    logger.info("✓ Created incidents collection with indexes")

    logger.info("✓ Database initialization complete")


def close_database():
    """Close the MongoDB connection."""
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("✓ MongoDB connection closed")
