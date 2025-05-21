from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import os
import json

class MetadataCacheInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    image_id: str = Field(..., description="Unique image ID (filename or hash) for the uploaded image.")
    metadata_json: str = Field(..., description="Raw JSON string of extracted metadata from MetadataExtractionAgent.")

class MetadataCacheTool(BaseTool):
    name: str = "Session Metadata Cache Tool"
    description: str = (
        "Stores extracted image metadata in a Redis-backed session store. "
        "Takes session_id, image_id, and metadata_json (as string) and caches the metadata for follow-up queries."
    )
    args_schema: Type[BaseModel] = MetadataCacheInput

    def _run(self, session_id: str, image_id: str, metadata_json: str) -> str:
        try:
            # Parse the metadata JSON string
            metadata = json.loads(metadata_json)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Invalid metadata JSON: {e}"
            })
        try:
            store = SessionStore()
            store.set_metadata(session_id, image_id, metadata)
            return json.dumps({
                "success": True,
                "message": f"Metadata for image {image_id} cached successfully in session {session_id}."
            })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to cache metadata: {e}"
            })
