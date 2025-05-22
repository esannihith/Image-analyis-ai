# app/tools/session_retrieval_tool.py
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from app.store.session_store import SessionStore, SessionStoreError
import yaml
from pathlib import Path
import os
import json

# Load configuration from tools.yaml or environment variables
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        tool_config = yaml.safe_load(f).get("CoreTools", {}).get("SessionRetrievalTool", {}).get("config", {})
except Exception: 
    tool_config = {}

class SessionRetrievalInput(BaseModel):
    session_id: str = Field(..., description="The active session identifier.")
    action: str = Field(
        ..., 
        description="Specific action: 'get_ordered_images', 'get_last_n_images', 'get_image_by_index', 'get_image_by_hash', 'get_context_data', 'store_context_data', 'get_image_interaction_context'"
    )
    # Optional fields, applicability depends on the action
    image_hash: Optional[str] = Field(None, description="Image hash for 'get_image_by_hash' or to indicate current focus for 'get_image_interaction_context'.")
    n: Optional[int] = Field(None, description="Number of images for 'get_last_n_images'. Defaults to max_history_depth_config if not set for this action.")
    index: Optional[int] = Field(None, description="0-based index for 'get_image_by_index' (positive from start, negative from end).")
    context_key: Optional[str] = Field(None, description="Key for 'get_context_data' or 'store_context_data'.")
    context_data: Optional[Dict[str, Any]] = Field(None, description="Data dictionary for 'store_context_data'.")


class SessionRetrievalTool(BaseTool):
    name: str = "Session Data Retrieval and Storage Tool"
    description: str = """
    Retrieves and stores various types of session-specific data from Redis via SessionStore.
    Actions include: fetching ordered image sequences, last N images, image by index or hash,
    getting/setting generic session context data, and generating comprehensive image interaction context.
    Requires a 'session_id' and an 'action'.
    """
    args_schema: Type[BaseModel] = SessionRetrievalInput
    
    max_history_depth_config: int = tool_config.get("max_history_depth", int(os.getenv("SESSION_MAX_HISTORY_DEPTH", 10)))
    
    _session_store: SessionStore

    def __init__(self, session_store: Optional[SessionStore] = None, **kwargs):
        super().__init__(**kwargs)
        if session_store:
            self._session_store = session_store
        else:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                print("Warning: REDIS_URL environment variable not set. SessionStore will use default Redis URL.")
            self._session_store = SessionStore(redis_url=redis_url)

    @property
    def session_store(self) -> SessionStore:
        if not hasattr(self, '_session_store') or self._session_store is None:
            print("Error: SessionStore not initialized in SessionRetrievalTool. Attempting re-init.")
            self._session_store = SessionStore(redis_url=os.getenv("REDIS_URL"))
        return self._session_store

    def _run_action(self, session_id: str, action: str, image_hash: Optional[str], 
                  n: Optional[int], index: Optional[int], 
                  context_key: Optional[str], context_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data: Any = None
        error_msg: Optional[str] = None
        success = True
        action_details: Dict[str, Any] = {"action": action, "session_id": session_id}

        try:
            if not session_id:
                 raise ValueError("'session_id' is required.")

            if action == "get_ordered_images":
                images = self.session_store.get_session_images(session_id)
                action_details["count"] = len(images)
                if image_hash: 
                    action_details["current_image_hash_provided"] = image_hash
                    action_details["current_image_index"] = next((i for i, img in enumerate(images) if img.get("hash") == image_hash), -1)
                data = images
            
            elif action == "get_last_n_images":
                limit = n if n is not None and n > 0 else self.max_history_depth_config
                action_details["limit_used"] = limit
                images = self.session_store.get_session_images(session_id)
                data = images[-limit:] if images else []
            
            elif action == "get_image_by_index":
                if index is None:
                    raise ValueError("'index' parameter is required for 'get_image_by_index' action.")
                action_details["requested_index"] = index
                images = self.session_store.get_session_images(session_id)
                if not images:
                    data = None 
                    error_msg = "No images in session to retrieve by index." 
                    success = True
                elif -len(images) <= index < len(images):
                    data = images[index]
                else:
                    error_msg = f"Index {index} out of range for {len(images)} images."
                    success = False
            
            elif action == "get_image_by_hash":
                if not image_hash:
                    raise ValueError("'image_hash' parameter is required for 'get_image_by_hash' action.")
                action_details["requested_hash"] = image_hash
                data = self.session_store.get_image_metadata(session_id, image_hash) 
                if data is None:
                    success = True
                    error_msg = f"Image with hash '{image_hash}' not found in session '{session_id}'."

            elif action == "get_image_interaction_context":
                images_in_session = self.session_store.get_session_images(session_id)
                
                image_sequence = []
                for i, img_data in enumerate(images_in_session):
                    image_sequence.append({
                        "id": img_data.get("hash"),
                        "original_filename": img_data.get("filename", "N/A"),
                        "timestamp": img_data.get("upload_timestamp", img_data.get("timestamp")),
                        "order": i + 1
                    })

                current_image_focus_id: Optional[str] = None
                if image_hash and any(img.get("hash") == image_hash for img in images_in_session):
                    current_image_focus_id = image_hash
                elif images_in_session:
                    current_image_focus_id = images_in_session[-1].get("hash")

                image_aliases: Dict[str, Optional[str]] = {}
                if images_in_session:
                    last_image_hash = images_in_session[-1].get("hash")
                    first_image_hash = images_in_session[0].get("hash")

                    image_aliases["this image"] = current_image_focus_id
                    image_aliases["current image"] = current_image_focus_id
                    image_aliases["latest image"] = last_image_hash
                    image_aliases["most recent image"] = last_image_hash
                    image_aliases["last image"] = last_image_hash
                    image_aliases["first image"] = first_image_hash
                    
                    if current_image_focus_id:
                        try:
                            current_idx = next(i for i, img in enumerate(images_in_session) if img.get("hash") == current_image_focus_id)
                            if current_idx > 0:
                                image_aliases["previous image"] = images_in_session[current_idx - 1].get("hash")
                            if current_idx < len(images_in_session) - 1:
                                image_aliases["next image"] = images_in_session[current_idx + 1].get("hash")
                        except StopIteration:
                            pass

                    for i, img_data in enumerate(images_in_session):
                        image_aliases[f"image {i+1}"] = img_data.get("hash")
                        image_aliases[f"image_{i+1}"] = img_data.get("hash")
                        if img_data.get("filename"):
                            image_aliases[img_data.get("filename")] = img_data.get("hash")

                data = {
                    "image_sequence": image_sequence,
                    "current_image_focus": current_image_focus_id,
                    "image_aliases": image_aliases,
                    "total_images_in_session": len(images_in_session)
                }
                action_details["current_focus_used"] = current_image_focus_id
                action_details["aliases_generated"] = len(image_aliases)

            elif action == "get_context_data":
                if not context_key:
                    raise ValueError("'context_key' parameter is required for 'get_context_data' action.")
                action_details["context_key"] = context_key
                data = self.session_store.get_session_context(session_id, context_key)
                if data is None:
                    action_details["status"] = "key_not_found"

            elif action == "store_context_data":
                if not context_key:
                    raise ValueError("'context_key' parameter is required for 'store_context_data' action.")
                if context_data is None: 
                    raise ValueError("'context_data' (as a dictionary) is required for 'store_context_data' action.")
                action_details["context_key"] = context_key
                self.session_store.update_session_context(session_id, context_key, context_data)
                data = {"status": "stored", "key": context_key, "data_preview": str(context_data)[:100]} 
            
            else:
                success = False
                error_msg = f"Unknown action: {action}"

        except SessionStoreError as e:
            success = False
            error_msg = f"SessionStore Error performing action '{action}' (Code: {e.code}): {str(e)}"
        except ValueError as e: 
            success = False
            error_msg = f"Input Error for action '{action}': {str(e)}"
        except Exception as e:
            success = False
            error_msg = f"Unexpected error in SessionRetrievalTool action '{action}': {str(e)}"
            import traceback
            action_details["exception_trace"] = traceback.format_exc(limit=3)

        if success:
            return {"success": True, "action_details": action_details, "data": data}
        else:
            action_details["error_message"] = str(error_msg) if error_msg else "Unknown error"
            return {"success": False, "action_details": action_details, "error": str(error_msg) if error_msg is not None else "Unknown error in SessionRetrievalTool", "data": None}

    def _run(self, session_id: str, action: str, 
             image_hash: Optional[str] = None, 
             n: Optional[int] = None, 
             index: Optional[int] = None, 
             context_key: Optional[str] = None, 
             context_data: Optional[Dict[str, Any]] = None) -> str:
        
        result = self._run_action(
            session_id=session_id,
            action=action, 
            image_hash=image_hash, 
            n=n, 
            index=index, 
            context_key=context_key, 
            context_data=context_data
        )
        return json.dumps(result, default=str)