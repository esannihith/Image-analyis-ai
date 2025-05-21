from crewai.tools import BaseTool
from typing import Type, Optional
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import json

class PromptEnrichmentInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    user_question: str = Field(..., description="The user's natural language query.")
    image_id: Optional[str] = Field(None, description="Optional explicit image ID if already resolved.")

class PromptEnrichmentTool(BaseTool):
    name: str = "Prompt Enrichment Tool"
    description: str = (
        "Normalizes user queries by resolving ambiguous references (e.g., 'this image', 'first image', 'last image') "
        "to explicit image IDs using session metadata context. Returns a normalized prompt."
    )
    args_schema: Type[BaseModel] = PromptEnrichmentInput

    def _run(self, session_id: str, user_question: str, image_id: Optional[str] = None) -> str:
        store = SessionStore()
        metadata = store.get_all_metadata(session_id)
        resolved_image_id = image_id
        normalized_question = user_question
        if not resolved_image_id:
            image_keys = list(metadata.keys()) if metadata else []
            lower_q = user_question.lower()
            # Handle 'this image' or 'current image'
            if ("this image" in lower_q or "current image" in lower_q) and image_keys:
                resolved_image_id = image_keys[-1]
                normalized_question = lower_q.replace("this image", f"image {resolved_image_id}").replace("current image", f"image {resolved_image_id}")
            # Handle ordinal references
            ordinal_mapping = {
                "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
                "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
                "last": -1
            }
            for ordinal, index in ordinal_mapping.items():
                pattern = f"{ordinal} image"
                if pattern in lower_q and image_keys and (0 <= index < len(image_keys) or index == -1):
                    idx = index if index >= 0 else -1
                    resolved_image_id = image_keys[idx]
                    normalized_question = lower_q.replace(pattern, f"image {resolved_image_id}")
                    break
        return json.dumps({
            "normalized_question": normalized_question,
            "resolved_image_id": resolved_image_id,
            "success": True
        })
