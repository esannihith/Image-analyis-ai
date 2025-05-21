import os
import json
import redis
from typing import Any, Optional
from datetime import timedelta

class SessionStore:
    """
    Redis-backed session store for ephemeral image metadata and session data.
    Enhanced with error handling, connection testing, consistent JSON serialization,
    and namespacing for non-metadata fields.
    """
    METADATA_PREFIX = 'img:'
    FIELD_PREFIX = 'field:'

    def __init__(self, redis_url: Optional[str] = None, session_ttl: Optional[int] = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL')
        self.session_ttl = session_ttl or int(os.getenv('REDIS_SESSION_TTL', 86400))
        try:
            self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._test_connection()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}")

    def _test_connection(self):
        try:
            self.client.ping()
        except Exception as e:
            raise RuntimeError(f"Redis connection test failed: {e}")

    def _session_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def _serialize(self, data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except Exception as e:
            raise ValueError(f"Serialization error: {e}")

    def _deserialize(self, data: Optional[str]) -> Any:
        if data is None:
            return None
        try:
            return json.loads(data)
        except Exception as e:
            raise ValueError(f"Deserialization error: {e}")

    def set_metadata(self, session_id: str, image_id: str, metadata: dict) -> None:
        key = self._session_key(session_id)
        field = f"{self.METADATA_PREFIX}{image_id}"
        try:
            self.client.hset(key, field, self._serialize(metadata))
            self.client.expire(key, self.session_ttl)
        except Exception as e:
            raise RuntimeError(f"Failed to set metadata: {e}")

    def get_metadata(self, session_id: str, image_id: str) -> Optional[dict]:
        key = self._session_key(session_id)
        field = f"{self.METADATA_PREFIX}{image_id}"
        try:
            data = self.client.hget(key, field)
            return self._deserialize(data)
        except Exception as e:
            raise RuntimeError(f"Failed to get metadata: {e}")

    def get_all_metadata(self, session_id: str) -> dict:
        key = self._session_key(session_id)
        try:
            all_data = self.client.hgetall(key)
            # Only return fields with the metadata prefix
            return {
                img_id[len(self.METADATA_PREFIX):]: self._deserialize(meta)
                for img_id, meta in all_data.items()
                if img_id.startswith(self.METADATA_PREFIX)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get all metadata: {e}")

    def delete_image(self, session_id: str, image_id: str) -> None:
        key = self._session_key(session_id)
        field = f"{self.METADATA_PREFIX}{image_id}"
        try:
            self.client.hdel(key, field)
        except Exception as e:
            raise RuntimeError(f"Failed to delete image metadata: {e}")

    def clear_session(self, session_id: str) -> None:
        key = self._session_key(session_id)
        try:
            self.client.delete(key)
        except Exception as e:
            raise RuntimeError(f"Failed to clear session: {e}")

    def set_value(self, session_id: str, field: str, value: Any) -> None:
        key = self._session_key(session_id)
        namespaced_field = f"{self.FIELD_PREFIX}{field}"
        try:
            self.client.hset(key, namespaced_field, self._serialize(value))
            self.client.expire(key, self.session_ttl)
        except Exception as e:
            raise RuntimeError(f"Failed to set session field: {e}")

    def get_value(self, session_id: str, field: str) -> Optional[Any]:
        key = self._session_key(session_id)
        namespaced_field = f"{self.FIELD_PREFIX}{field}"
        try:
            data = self.client.hget(key, namespaced_field)
            return self._deserialize(data)
        except Exception as e:
            raise RuntimeError(f"Failed to get session field: {e}")

    def touch_session(self, session_id: str) -> None:
        """
        Refresh the TTL for a session key in Redis.
        """
        key = self._session_key(session_id)
        try:
            self.client.expire(key, self.session_ttl)
        except Exception as e:
            raise RuntimeError(f"Failed to refresh session TTL: {e}")
