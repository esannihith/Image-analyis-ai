import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, Optional, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import redis # Import redis directly for type hinting if needed, though SessionStore handles connection
from app.store.session_store import SessionStore # Assuming SessionStore is in app.store

# Static variable to cache the loaded lens data
_lens_data_cache: Optional[List[Dict[str, Any]]] = None
_lens_data_file_path: Path = Path(__file__).parent.parent / "config" / "data" / "lenses.json"

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path, 'r', encoding='utf-8') as f: # Specify encoding
        tool_config = yaml.safe_load(f)["TechnicalTools"]["LensDatabase"]["config"]
except Exception:
    tool_config = {}

class LensDatabaseInput(BaseModel):
    """Input schema for LensDatabaseTool."""
    lens_make: Optional[str] = Field(None, description="The make of the lens (e.g., 'Canon', 'NIKON'). Extracted from EXIF.")
    lens_model: Optional[str] = Field(None, description="The model name/identifier of the lens (e.g., 'EF24-70mm f/2.8L II USM'). Extracted from EXIF.")
    # Fallback if a single LensID tag is available and preferred
    lens_id_tag: Optional[str] = Field(None, description="A unique lens identifier string directly from EXIF tag (e.g., from LensID or LensModel tag value).")

class LensDatabaseTool(BaseTool):
    name: str = "Lens Database Querier"
    description: str = (
        "Provides detailed characteristics for a given lens model by querying a bundled JSON lens database, "
        "utilizing a Redis cache for performance. Input can be lens make/model or a direct lens ID tag from EXIF."
    )
    args_schema: Type[BaseModel] = LensDatabaseInput

    cache_ttl_config: int = tool_config.get("cache_ttl", int(os.getenv("LENSDB_CACHE_TTL", 3600)))
    # The 'storage: redis' config is implicitly handled by using SessionStore for Redis connection.

    def __init__(self, session_store: Optional[SessionStore] = None, **kwargs):
        super().__init__(**kwargs)
        self._session_store = session_store if session_store else SessionStore()
        try:
            # It's good practice for SessionStore to provide a method for this.
            # If _get_connection is a protected member, ensure this usage is acceptable or refactor SessionStore.
            self.redis_conn = self._session_store._get_connection() 
        except Exception as e:
            # Fallback if redis connection fails, tool can still work from JSON file but without caching
            self.redis_conn = None 
            print(f"Warning: LensDatabaseTool could not connect to Redis. Caching will be disabled. Error: {e}")
        
        self._load_lens_data_from_file() # Load data when tool is initialized

    def _normalize_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return "".join(filter(str.isalnum, text.lower()))

    def _generate_cache_key(self, lens_make: Optional[str], lens_model: Optional[str], lens_id_tag: Optional[str]) -> Optional[str]:
        norm_id_tag = self._normalize_text(lens_id_tag)
        if norm_id_tag:
            return f"lensdb:id:{norm_id_tag}"
        
        norm_make = self._normalize_text(lens_make)
        norm_model = self._normalize_text(lens_model)
        if norm_make and norm_model:
            return f"lensdb:mkmd:{norm_make}:{norm_model}"
        if norm_model: # Fallback to just model if make is missing but model is descriptive
             return f"lensdb:md:{norm_model}"
        return None

    def _load_lens_data_from_file(self):
        global _lens_data_cache
        if _lens_data_cache is not None:
            return

        if not _lens_data_file_path.is_file():
            print(f"Warning: Lens data file not found at {_lens_data_file_path}. LensDatabaseTool will not find any lenses.")
            _lens_data_cache = [] # Set to empty list to avoid re-attempts
            return

        try:
            with open(_lens_data_file_path, 'r', encoding='utf-8') as f:
                _lens_data_cache = json.load(f)
            if not isinstance(_lens_data_cache, list):
                print(f"Warning: Lens data file at {_lens_data_file_path} is not a JSON list. Resetting cache.")
                _lens_data_cache = []
        except json.JSONDecodeError:
            print(f"Warning: Error decoding JSON from lens data file at {_lens_data_file_path}. Resetting cache.")
            _lens_data_cache = []
        except Exception as e:
            print(f"Warning: Failed to load lens data file {_lens_data_file_path}: {e}. Resetting cache.")
            _lens_data_cache = []


    def _fetch_lens_data_from_loaded_json(self, normalized_make: str, normalized_model: str, normalized_id_tag: str) -> Optional[Dict[str, Any]]:
        global _lens_data_cache
        if _lens_data_cache is None: # Should have been loaded by __init__
            self._load_lens_data_from_file()
        if not _lens_data_cache: # If still no data (e.g. file not found or empty)
            return None

        # Prioritize ID tag if provided and matches a search key
        if normalized_id_tag:
            for lens in _lens_data_cache:
                search_keys = lens.get("search_keys", [])
                if isinstance(search_keys, list) and normalized_id_tag in search_keys:
                    return lens
                # Also check if the ID tag directly matches a normalized model if no specific search_keys for ID
                if self._normalize_text(lens.get("model_db")) == normalized_id_tag:
                     return lens


        # Then try make and model
        if normalized_make and normalized_model:
            for lens in _lens_data_cache:
                db_make_norm = self._normalize_text(lens.get("make_db"))
                # Check against search_keys first for model
                model_match_in_search_keys = False
                for sk in lens.get("search_keys", []):
                    if self._normalize_text(sk) == normalized_model:
                        model_match_in_search_keys = True
                        break
                
                # Check against normalized model_db as well
                db_model_norm = self._normalize_text(lens.get("model_db"))

                if db_make_norm == normalized_make and (db_model_norm == normalized_model or model_match_in_search_keys) :
                    return lens
        
        # Fallback to just model if make was not provided or didn't lead to a match with model
        if normalized_model:
             for lens in _lens_data_cache:
                model_match_in_search_keys = False
                for sk in lens.get("search_keys", []):
                    if self._normalize_text(sk) == normalized_model:
                        model_match_in_search_keys = True
                        break
                db_model_norm = self._normalize_text(lens.get("model_db"))
                if db_model_norm == normalized_model or model_match_in_search_keys:
                    return lens
        return None

    def _run(self, lens_make: Optional[str] = None, lens_model: Optional[str] = None, lens_id_tag: Optional[str] = None) -> str:
        response_data: Dict[str, Any]
        
        cache_key = self._generate_cache_key(lens_make, lens_model, lens_id_tag)

        if not cache_key: # Should not happen if at least model or id_tag is usually present from EXIF
            response_data = {"success": False, "error": "Insufficient lens identification information (need model or ID tag)."}
            return json.dumps(response_data)

        # Try Redis cache first if connection is available
        if self.redis_conn:
            try:
                cached_data = self.redis_conn.get(cache_key)
                if cached_data:
                    lens_info = json.loads(cached_data.decode('utf-8')) # Ensure decoding from bytes
                    response_data = {"success": True, "lens_info": lens_info, "cache_status": "hit", "source": "redis_cache", "cache_key_used": cache_key}
                    return json.dumps(response_data)
            except redis.RedisError as e:
                print(f"Warning: Redis GET operation failed for LensDatabaseTool: {e}") # Log but continue to file lookup
            except json.JSONDecodeError as e:
                 print(f"Warning: JSON decoding error for cached lens data (key: {cache_key}): {e}")


        # If not in Redis cache or Redis failed, fetch from loaded JSON data
        norm_make = self._normalize_text(lens_make)
        norm_model = self._normalize_text(lens_model)
        norm_id_tag = self._normalize_text(lens_id_tag)
        
        lens_info = self._fetch_lens_data_from_loaded_json(norm_make, norm_model, norm_id_tag)

        if lens_info:
            if self.redis_conn: # Try to cache it if Redis is available
                try:
                    self.redis_conn.setex(cache_key, self.cache_ttl_config, json.dumps(lens_info))
                except redis.RedisError as e:
                    print(f"Warning: Redis SETEX operation failed for LensDatabaseTool: {e}") # Log but proceed

            response_data = {"success": True, "lens_info": lens_info, "cache_status": "miss", "source": "json_file", "cache_key_used": cache_key}
        else:
            response_data = {
                "success": False, 
                "error": "Lens details not found in the bundled JSON database for the provided identifiers.",
                "query_details": {"lens_make": lens_make, "lens_model": lens_model, "lens_id_tag": lens_id_tag},
                "normalized_query": {"make": norm_make, "model": norm_model, "id_tag": norm_id_tag},
                "cache_key_attempted": cache_key,
                "source": "json_file"
            }
            
        return json.dumps(response_data, default=str) # Use default=str for any non-serializable types
