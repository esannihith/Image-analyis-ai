from crewai.tools import BaseTool
from typing import Type, Optional
from pydantic import BaseModel, Field
from app.store.session_store import SessionStore
import json

"""
Prompt enrichment tool for CrewAI. Normalizes user queries by resolving ambiguous references to explicit image IDs.
Returns output matching the standardized schema: {"normalized_query": <str>, "resolved_image_ids": <list>, "success": <bool>, "error": <str|null>}.
"""

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
        """
        Normalize user query and resolve image references. Returns standardized output.
        """
        try:
            store = SessionStore()
            metadata = store.get_all_metadata(session_id)
            resolved_image_ids = []
            normalized_query = user_question
            if image_id:
                resolved_image_ids = [image_id]
            else:
                image_keys = list(metadata.keys()) if metadata else []
                lower_q = user_question.lower()
                if ("this image" in lower_q or "current image" in lower_q) and image_keys:
                    resolved_image_ids = [image_keys[-1]]
                    normalized_query = lower_q.replace("this image", f"image {image_keys[-1]}").replace("current image", f"image {image_keys[-1]}")
                ordinal_mapping = {
                    "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
                    "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
                    "last": -1
                }
                for ordinal, index in ordinal_mapping.items():
                    pattern = f"{ordinal} image"
                    if pattern in lower_q and image_keys and (0 <= index < len(image_keys) or index == -1):
                        idx = index if index >= 0 else -1
                        resolved_image_ids = [image_keys[idx]]
                        normalized_query = lower_q.replace(pattern, f"image {image_keys[idx]}")
                        break
            return json.dumps({
                "normalized_query": normalized_query,
                "resolved_image_ids": resolved_image_ids,
                "success": True,
                "error": None
            })
        except Exception as e:
            return json.dumps({
                "normalized_query": user_question,
                "resolved_image_ids": [],
                "success": False,
                "error": str(e)
            })
