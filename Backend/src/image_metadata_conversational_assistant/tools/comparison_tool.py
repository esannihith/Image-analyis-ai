from crewai.tools import BaseTool
from typing import Type, Dict, Any
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import json

class ComparisonInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    image_id_1: str = Field(..., description="First image ID to compare.")
    image_id_2: str = Field(..., description="Second image ID to compare.")

class ComparisonTool(BaseTool):
    name: str = "Comparison Tool"
    description: str = (
        "Compares metadata (ISO, aperture, shutter-speed, etc.) between two images in the session and returns a structured difference."
    )
    args_schema: Type[BaseModel] = ComparisonInput

    def _run(self, session_id: str, image_id_1: str, image_id_2: str) -> str:
        store = SessionStore()
        all_metadata = store.get_all_metadata(session_id)
        meta1 = all_metadata.get(image_id_1)
        meta2 = all_metadata.get(image_id_2)
        if not meta1 or not meta2:
            return json.dumps({"success": False, "error": "One or both images not found in session."})
        # Flatten metadata for both images
        def flatten(meta):
            row = {}
            if 'processed_data' in meta:
                for section, section_data in meta['processed_data'].items():
                    if isinstance(section_data, dict):
                        for k, v in section_data.items():
                            row[f"{section}_{k}"] = v
                    else:
                        row[section] = section_data
            for k, v in meta.items():
                if k != 'processed_data':
                    row[k] = v
            return row
        row1 = flatten(meta1)
        row2 = flatten(meta2)
        # Compare relevant fields
        fields = set(row1.keys()).union(row2.keys())
        differences = {}
        for field in fields:
            v1 = row1.get(field)
            v2 = row2.get(field)
            if v1 != v2:
                differences[field] = {"image_1": v1, "image_2": v2}
        return json.dumps({
            "success": True,
            "image_1": image_id_1,
            "image_2": image_id_2,
            "differences": differences
        })
