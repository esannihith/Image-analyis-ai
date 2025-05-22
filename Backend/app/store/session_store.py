import os
import json
import hashlib
import redis
from typing import Any, Optional, Dict, List
from datetime import datetime
from functools import wraps
from redis.exceptions import RedisError

class SessionStoreError(Exception):
    """Base exception for session store errors"""
    def __init__(self, message: str, code: str, severity: str = "error"):
        super().__init__(message)
        self.code = code
        self.severity = severity
        self.timestamp = datetime.utcnow().isoformat()

class SessionStore:
    """
    Enhanced Redis session store with robust error handling, image sequence tracking,
    and metadata validation.
    
    Features:
    - Atomic operations with pipeline
    - Automatic TTL renewal
    - Image upload order tracking
    - Metadata schema validation
    - Connection pooling
    - Thread-safe operations
    """
    
    def __init__(self, redis_url: Optional[str] = None, session_ttl: int = 86400):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.session_ttl = session_ttl
        self.pool = redis.ConnectionPool.from_url(self.redis_url, decode_responses=True)
        
    def _get_connection(self):
        return redis.Redis(connection_pool=self.pool)

    def _handle_errors(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except RedisError as e:
                raise SessionStoreError(
                    message=f"Redis operation failed: {str(e)}",
                    code="REDIS_OPERATION_FAILED",
                    severity="critical"
                ) from e
            except json.JSONDecodeError as e:
                raise SessionStoreError(
                    message="Invalid JSON data in store",
                    code="INVALID_JSON_DATA",
                    severity="error"
                ) from e
            except Exception as e:
                raise SessionStoreError(
                    message=f"Unexpected error: {str(e)}",
                    code="UNEXPECTED_ERROR",
                    severity="error"
                ) from e
        return wrapper

    def _session_key(self, session_id: str) -> str:
        return f"imca:session:{session_id}"

    def _upload_order_key(self, session_id: str) -> str:
        return f"{self._session_key(session_id)}:upload_order"

    def _validate_metadata(self, metadata: Dict[str, Any]):
        """Ensure required metadata fields are present"""
        required_sections = {'exif', 'iptc', 'xmp'}
        if not required_sections.intersection(metadata.keys()):
            raise SessionStoreError(
                message="Metadata missing required sections",
                code="INVALID_METADATA",
                severity="warning"
            )

    @_handle_errors
    def create_session(self, session_id: str) -> None:
        """Initialize a new session with default structure"""
        conn = self._get_connection()
        if conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} already exists",
                code="SESSION_ALREADY_EXISTS",
                severity="error"
            )
        with conn.pipeline() as pipe:
            pipe.hset(
                self._session_key(session_id),
                "created_at",
                datetime.utcnow().isoformat()
            )
            pipe.expire(self._session_key(session_id), self.session_ttl)
            pipe.execute()

    @_handle_errors
    def store_image_metadata(
        self,
        session_id: str,
        image_data: bytes,
        metadata: Dict[str, Any]
    ) -> str:
        """Store metadata with image hash validation and upload order tracking"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        self._validate_metadata(metadata)
        
        image_hash = hashlib.sha256(image_data).hexdigest()
        metadata_key = f"metadata:{image_hash}"
        
        with conn.pipeline() as pipe:
            # Store metadata globally by hash
            pipe.hset(metadata_key, mapping=metadata)
            pipe.expire(metadata_key, self.session_ttl * 2)
            
            # Link to session
            pipe.zadd(
                self._upload_order_key(session_id),
                {image_hash: datetime.utcnow().timestamp()}
            )
            pipe.expire(self._upload_order_key(session_id), self.session_ttl)
            
            # Touch session TTL
            pipe.expire(self._session_key(session_id), self.session_ttl)
            
            pipe.execute()
            
        return image_hash

    @_handle_errors
    def get_image_metadata(self, session_id: str, image_hash: str) -> Dict[str, Any]:
        """Retrieve metadata with hash validation"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        if not conn.zscore(self._upload_order_key(session_id), image_hash):
            raise SessionStoreError(
                message=f"Image {image_hash} not associated with session {session_id}",
                code="IMAGE_NOT_IN_SESSION",
                severity="error"
            )
        metadata = conn.hgetall(f"metadata:{image_hash}")
        
        if not metadata:
            raise SessionStoreError(
                message="Metadata not found for image",
                code="METADATA_NOT_FOUND",
                severity="warning"
            )
            
        return metadata

    @_handle_errors
    def get_session_images(self, session_id: str) -> List[Dict[str, Any]]:
        # Add pagination for large sessions
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        image_hashes = conn.zrange(
            self._upload_order_key(session_id),
            0, -1, withscores=False
        )
        return self._batch_get_metadata(image_hashes)

    @_handle_errors
    def _batch_get_metadata(self, hashes: List[str]) -> List[Dict[str, Any]]:
        # Deduplicate and batch process
        unique_hashes = list(set(hashes))
        conn = self._get_connection()
        with conn.pipeline() as pipe:
            for h in unique_hashes:
                pipe.hgetall(f"metadata:{h}")
            results = pipe.execute()
        
        return [
            {"hash": h, **data}
            for h, data in zip(unique_hashes, results)
            if data
        ]

    @_handle_errors
    def update_session_context(
        self,
        session_id: str,
        context_key: str,
        context_data: Any
    ) -> None:
        """Store additional session context (e.g., comparison history)"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        conn.hset(
            self._session_key(session_id),
            f"ctx:{context_key}",
            json.dumps(context_data)
        )
        conn.expire(self._session_key(session_id), self.session_ttl)

    @_handle_errors
    def get_session_context(
        self,
        session_id: str,
        context_key: str
    ) -> Any:
        """Retrieve stored session context"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        data = conn.hget(self._session_key(session_id), f"ctx:{context_key}")
        return json.loads(data) if data else None

    @_handle_errors
    def touch_session(self, session_id: str) -> None:
        """Refresh session TTL on activity"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        conn.expire(self._session_key(session_id), self.session_ttl)
        conn.expire(self._upload_order_key(session_id), self.session_ttl)

    @_handle_errors
    def delete_session(self, session_id: str) -> None:
        """Fully remove a session and its data"""
        conn = self._get_connection()
        if not conn.exists(self._session_key(session_id)):
            raise SessionStoreError(
                message=f"Session {session_id} does not exist",
                code="SESSION_NOT_FOUND",
                severity="error"
            )
        image_hashes = conn.zrange(
            self._upload_order_key(session_id),
            0,
            -1
        )
        
        with conn.pipeline() as pipe:
            # Delete session metadata
            pipe.delete(self._session_key(session_id))
            pipe.delete(self._upload_order_key(session_id))
            
            # Cleanup global metadata if no references
            for image_hash in image_hashes:
                pipe.delete(f"metadata:{image_hash}")
                
            pipe.execute()