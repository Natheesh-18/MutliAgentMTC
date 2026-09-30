"""Thread-safe singleton MongoDB client provider."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

import hvac
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from src.config import get_ca_file, get_ck_file

logger = logging.getLogger(__name__)

__all__ = [
    "MongoClientProvider",
    "mongo_provider",
    "get_sync_client",
    "get_async_client",
    "get_database",
    "get_collection",
    "resolve_mongo_url",
]


# ---------------------------------------------------------------------------
# Vault / URL resolution (single canonical implementation)
# ---------------------------------------------------------------------------

def resolve_mongo_url() -> str:
    """Resolve the MongoDB connection URL.

    On-prem deployments read from the ``mongodb_URL`` environment variable
    directly. Cloud deployments fetch the URL from HashiCorp Vault using
    AppRole authentication.

    Returns
    -------
    str
        The MongoDB connection string.

    Raises
    ------
    RuntimeError
        If the URL cannot be resolved from either source.
    """
    is_onprem = json.loads(os.getenv("isOnprem", "false").lower())

    if is_onprem:
        url = os.getenv("mongodb_URL")
        if not url:
            raise RuntimeError(
                "Environment variable 'mongodb_URL' is required in on-prem mode."
            )
        return url

    # Cloud mode — fetch from Vault
    vault_url = os.getenv("vault_URL")
    role_id = os.getenv("role_id")
    secret_id = os.getenv("secret_id")
    vault_path = os.getenv("vault_path")
    mongodb_url_key = os.getenv("mongodb_URL")

    if not all([vault_url, role_id, secret_id, vault_path, mongodb_url_key]):
        raise RuntimeError(
            "Vault configuration is incomplete. Required env vars: "
            "vault_URL, role_id, secret_id, vault_path, mongodb_URL."
        )

    vault_client = hvac.Client(url=vault_url)
    vault_client.auth.approle.login(role_id=role_id, secret_id=secret_id)

    try:
        secret = vault_client.secrets.kv.v2.read_secret_version(path=vault_path)
    except (hvac.exceptions.InvalidPath, hvac.exceptions.Forbidden):
        # Handle mount-point-prefixed paths (e.g. "mount/actual_path")
        mount_point, path = vault_path.split("/", 1)
        secret = vault_client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount_point
        )

    return secret["data"]["data"][mongodb_url_key]


# ---------------------------------------------------------------------------
# Singleton provider
# ---------------------------------------------------------------------------

class MongoClientProvider:
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sync_client: Optional[MongoClient] = None
        self._async_client: Optional[AsyncIOMotorClient] = None
        self._url: Optional[str] = None
        self._is_onprem: bool = False
        self._ca_file: Optional[str] = None
        self._ck_file: Optional[str] = None
        self._initialized: bool = False

    def initialize(
        self,
        url: Optional[str] = None,
        is_onprem: Optional[bool] = None,
        ca_file: Optional[str] = None,
        ck_file: Optional[str] = None,
    ) -> None:
        """Initialize the mongo client with connection parameters."""
        with self._lock:
            if self._initialized:
                logger.debug("MongoClientProvider is already initialized — skipping.")
                return

            self._is_onprem = (
                is_onprem
                if is_onprem is not None
                else json.loads(os.getenv("isOnprem", "false").lower())
            )
            self._url = url or resolve_mongo_url()
            self._ca_file = ca_file if ca_file is not None else get_ca_file()
            self._ck_file = ck_file if ck_file is not None else get_ck_file()

            # -- Create sync client (pymongo) --------------------------------
            self._sync_client = self._build_sync_client()
            logger.info(
                "Sync MongoClient created (%s mode).",
                "on-prem" if self._is_onprem else "cloud/TLS",
            )

            # -- Create async client (motor) ---------------------------------
            self._async_client = self._build_async_client()
            logger.info(
                "Async MongoClient (Motor) created (%s mode).",
                "on-prem" if self._is_onprem else "cloud/TLS",
            )

            self._initialized = True
            logger.info("MongoClientProvider initialized successfully.")

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def close(self) -> None:
        """Close both the sync and async clients and reset the provider."""
        with self._lock:
            if self._sync_client is not None:
                self._sync_client.close()
                logger.info("Sync MongoClient closed.")
                self._sync_client = None

            if self._async_client is not None:
                self._async_client.close()
                logger.info("Async MongoClient (Motor) closed.")
                self._async_client = None

            self._initialized = False

    # -- Accessors -----------------------------------------------------------

    def get_sync_client(self) -> MongoClient:
        """Return the singleton ``pymongo.MongoClient``."""
        if not self._initialized or self._sync_client is None:
            self._ensure_initialized()
        return self._sync_client

    def get_async_client(self) -> AsyncIOMotorClient:
        """Return the singleton ``motor.AsyncIOMotorClient``."""
        if not self._initialized or self._async_client is None:
            self._ensure_initialized()
        return self._async_client

    def get_database(self, db_name: str) -> Database:
        """Convenience: return a ``pymongo.Database`` by name."""
        return self.get_sync_client()[db_name]

    def get_collection(self, db_name: str, collection_name: str) -> Collection:
        """Convenience: return a ``pymongo.Collection`` by database and name."""
        return self.get_database(db_name)[collection_name]

    @property
    def url(self) -> Optional[str]:
        """The resolved MongoDB connection URL (read-only)."""
        if not self._initialized:
            self._ensure_initialized()
        return self._url

    @property
    def is_initialized(self) -> bool:
        """Whether :meth:`initialize` has been called successfully."""
        return self._initialized

    # -- Internal helpers ----------------------------------------------------

    def _build_sync_client(self) -> MongoClient:
        if self._is_onprem:
            return MongoClient(self._url)
        return MongoClient(
            self._url,
            tlsCAFile=self._ca_file,
            tlsCertificateKeyFile=self._ck_file,
        )

    def _build_async_client(self) -> AsyncIOMotorClient:
        if self._is_onprem:
            return AsyncIOMotorClient(self._url)
        return AsyncIOMotorClient(
            self._url,
            tlsCAFile=self._ca_file,
            tlsCertificateKeyFile=self._ck_file,
        )
# ---------------------------------------------------------------------------
# Module-level singleton instance & convenience functions
# ---------------------------------------------------------------------------

mongo_provider = MongoClientProvider()
"""The global singleton instance. Import and use this directly, or use the
module-level convenience functions below."""

def get_sync_client() -> MongoClient:
    """Return the singleton sync ``MongoClient``."""
    return mongo_provider.get_sync_client()

def get_async_client() -> AsyncIOMotorClient:
    """Return the singleton async ``AsyncIOMotorClient``."""
    return mongo_provider.get_async_client()

def get_database(db_name: str) -> Database:
    """Return a ``Database`` from the singleton sync client."""
    return mongo_provider.get_database(db_name)

def get_collection(db_name: str, collection_name: str) -> Collection:
    """Return a ``Collection`` from the singleton sync client."""
    return mongo_provider.get_collection(db_name, collection_name)
