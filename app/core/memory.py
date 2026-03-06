"""
Shared memory management for agent coordination.
Uses Redis when available, falls back to in-process dict for local development.
"""

import json
import logging
from typing import Any, Dict, Optional
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class SharedMemory:
    """
    Shared memory for agent communication.
    - Redis backend: used when Redis is reachable (production / staging).
    - In-memory dict fallback: used automatically when Redis is not available
      so the server runs fine locally without a Redis instance.
    """

    def __init__(self):
        self._client: Optional[aioredis.Redis] = None
        self._fallback: Dict[str, str] = {}   # local in-memory store
        self._use_redis = False
        self.default_ttl = 3600 * 24  # 24 hours

    async def connect(self):
        """Attempt Redis connection; silently fall back to in-memory on failure."""
        try:
            client = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,   # fail fast if Redis is not there
            )
            # Ping to verify the connection is actually alive
            await client.ping()
            self._client = client
            self._use_redis = True
            logger.info("SharedMemory connected to Redis [OK]")
        except Exception as e:
            self._use_redis = False
            logger.warning(
                f"Redis unavailable ({e}). "
                "SharedMemory falling back to in-process dict — "
                "workflow state will not persist across restarts. "
                "Start Redis to enable persistent shared memory."
            )

    async def close(self):
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        serialized = json.dumps(value, default=str)
        if self._use_redis:
            try:
                await self._client.set(key, serialized, ex=ttl or self.default_ttl)
                return
            except Exception as e:
                logger.warning(f"Redis set failed, using fallback: {e}")
                self._use_redis = False
        self._fallback[key] = serialized

    async def get(self, key: str) -> Optional[Any]:
        if self._use_redis:
            try:
                value = await self._client.get(key)
            except Exception as e:
                logger.warning(f"Redis get failed, using fallback: {e}")
                self._use_redis = False
                value = self._fallback.get(key)
        else:
            value = self._fallback.get(key)

        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def delete(self, key: str) -> None:
        if self._use_redis:
            try:
                await self._client.delete(key)
                return
            except Exception:
                self._use_redis = False
        self._fallback.pop(key, None)

    async def exists(self, key: str) -> bool:
        if self._use_redis:
            try:
                return bool(await self._client.exists(key))
            except Exception:
                self._use_redis = False
        return key in self._fallback

    async def get_workflow_data(self, workflow_id: str) -> dict:
        """Get all data stored for a workflow."""
        prefix = f"{workflow_id}:"
        if self._use_redis:
            try:
                keys = await self._client.keys(f"{prefix}*")
                result = {}
                for key in keys:
                    field = key.replace(prefix, "", 1)
                    result[field] = await self.get(key)
                return result
            except Exception:
                self._use_redis = False
        # Fallback: scan the local dict
        return {
            k.replace(prefix, "", 1): json.loads(v)
            for k, v in self._fallback.items()
            if k.startswith(prefix)
        }

    async def set_workflow_status(self, workflow_id: str, status: dict) -> None:
        await self.set(f"workflow_status:{workflow_id}", status, ttl=86400)

    async def get_workflow_status(self, workflow_id: str) -> Optional[dict]:
        return await self.get(f"workflow_status:{workflow_id}")

    async def clear_workflow(self, workflow_id: str) -> None:
        """Clear all keys for a workflow."""
        prefix = f"{workflow_id}:"
        if self._use_redis:
            try:
                keys = await self._client.keys(f"{prefix}*")
                if keys:
                    await self._client.delete(*keys)
                return
            except Exception:
                self._use_redis = False
        # Fallback
        keys_to_delete = [k for k in self._fallback if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._fallback[k]

    @property
    def backend(self) -> str:
        """Returns 'redis' or 'memory' — useful for health checks."""
        return "redis" if self._use_redis else "memory"


# Singleton instance
shared_memory = SharedMemory()