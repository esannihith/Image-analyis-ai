from crewai.tools import BaseTool
from typing import Type, Dict, Any
from pydantic import BaseModel, Field
from app.store.session_store import SessionStore
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

    """
    Comparison tool for CrewAI. Compares metadata between two images and returns differences.
    Returns output matching the standardized schema: {"comparison": <str>, "differences": <dict>, "image_ids": <list>, "success": <bool>, "error": <str|null>}.
    """
    def _run(self, session_id: str, image_id_1: str, image_id_2: str) -> str:
        """
        Compare metadata between two images. Returns standardized output.
        """
        try:
            store = SessionStore()
            all_metadata = store.get_all_metadata(session_id)
            meta1 = all_metadata.get(image_id_1)
            meta2 = all_metadata.get(image_id_2)
            if not meta1 or not meta2:
                return json.dumps({
                    "comparison": "",
                    "differences": {},
                    "image_ids": [image_id_1, image_id_2],
                    "success": False,
                    "error": "One or both images not found in session."
                })
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
            fields = set(row1.keys()).union(row2.keys())
            differences = {}
            for field in fields:
                v1 = row1.get(field)
                v2 = row2.get(field)
                if v1 != v2:
                    differences[field] = {"image_1": v1, "image_2": v2}
            comparison = f"Compared {image_id_1} and {image_id_2}. {len(differences)} fields differ."
            return json.dumps({
                "comparison": comparison,
                "differences": differences,
                "image_ids": [image_id_1, image_id_2],
                "success": True,
                "error": None
            })
        except Exception as e:
            return json.dumps({
                "comparison": "",
                "differences": {},
                "image_ids": [image_id_1, image_id_2],
                "success": False,
                "error": str(e)
            })
