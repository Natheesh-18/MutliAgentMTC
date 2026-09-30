"""Thread-safe singleton Qdrant client provider."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient, QdrantClient

load_dotenv()
logger = logging.getLogger(__name__)

__all__ = [
    "QdrantClientProvider",
    "qdrant_provider",
    "get_sync_qdrant_client",
    "get_async_qdrant_client",
]


# ---------------------------------------------------------------------------
# Singleton provider
# ---------------------------------------------------------------------------

class QdrantClientProvider:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sync_client: Optional[QdrantClient] = None
        self._async_client: Optional[AsyncQdrantClient] = None
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._initialized: bool = False

    def initialize(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """Initialize the Qdrant clients with connection parameters."""
        with self._lock:
            if self._initialized:
                logger.debug("QdrantClientProvider is already initialized — skipping.")
                return

            self._host = host or os.getenv("QDRANT_HOST")
            port_env = os.getenv("QDRANT_PORT")
            self._port = port if port is not None else (int(port_env) if port_env else None)

            self._sync_client = QdrantClient(
                self._host,
                port=self._port,
                https=False,
                check_compatibility=False,
            )
            logger.info("Sync QdrantClient created (host=%s, port=%s).", self._host, self._port)

            self._async_client = AsyncQdrantClient(
                self._host,
                port=self._port,
                https=False,
                timeout=60.0,
            )
            logger.info("Async QdrantClient created (host=%s, port=%s).", self._host, self._port)

            self._initialized = True
            logger.info("QdrantClientProvider initialized successfully.")

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def close(self) -> None:
        """Close both the sync and async clients and reset the provider."""
        with self._lock:
            if self._sync_client is not None:
                self._sync_client.close()
                logger.info("Sync QdrantClient closed.")
                self._sync_client = None

            if self._async_client is not None:
                asyncio_close = getattr(self._async_client, "close", None)
                if asyncio_close:
                    # AsyncQdrantClient.close() is sync in qdrant-client>=1.7
                    try:
                        asyncio_close()
                    except Exception:
                        pass
                logger.info("Async QdrantClient closed.")
                self._async_client = None

            self._initialized = False

    # -- Accessors -----------------------------------------------------------

    def get_sync_client(self) -> QdrantClient:
        """Return the singleton ``QdrantClient``."""
        if not self._initialized or self._sync_client is None:
            self._ensure_initialized()
        return self._sync_client

    def get_async_client(self) -> AsyncQdrantClient:
        """Return the singleton ``AsyncQdrantClient``."""
        if not self._initialized or self._async_client is None:
            self._ensure_initialized()
        return self._async_client

    @property
    def host(self) -> Optional[str]:
        """The Qdrant host (read-only)."""
        if not self._initialized:
            self._ensure_initialized()
        return self._host

    @property
    def port(self) -> Optional[int]:
        """The Qdrant port (read-only)."""
        if not self._initialized:
            self._ensure_initialized()
        return self._port

    @property
    def is_initialized(self) -> bool:
        """Whether :meth:`initialize` has been called successfully."""
        return self._initialized


# ---------------------------------------------------------------------------
# Module-level singleton instance & convenience functions
# ---------------------------------------------------------------------------

qdrant_provider = QdrantClientProvider()

def get_sync_qdrant_client() -> QdrantClient:
    """Return the singleton sync ``QdrantClient``."""
    return qdrant_provider.get_sync_client()

def get_async_qdrant_client() -> AsyncQdrantClient:
    """Return the singleton async ``AsyncQdrantClient``."""
    return qdrant_provider.get_async_client()
