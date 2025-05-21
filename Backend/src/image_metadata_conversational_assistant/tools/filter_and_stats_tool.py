from crewai.tools import BaseTool
from typing import Type, Optional, Dict, Any
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import json

class FilterAndStatsInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters to apply to image metadata (e.g., {'camera': 'Canon', 'location': 'Paris'}).")
    stats: Optional[Dict[str, str]] = Field(None, description="Optional statistics to compute (e.g., {'field': 'date', 'operation': 'min'}). Supported operations: count, min, max, unique.")

class FilterAndStatsTool(BaseTool):
    name: str = "Filter and Statistics Tool"
    description: str = (
        "Filters session metadata by criteria and computes basic statistics over the filtered set."
    )
    args_schema: Type[BaseModel] = FilterAndStatsInput

    def _run(self, session_id: str, filters: Optional[Dict[str, Any]] = None, stats: Optional[Dict[str, str]] = None) -> str:
        store = SessionStore()
        all_metadata = store.get_all_metadata(session_id)
        if not all_metadata:
            return json.dumps({"success": False, "error": f"No metadata found for session {session_id}."})
        # Flatten metadata for filtering
        rows = []
        for image_id, meta in all_metadata.items():
            row = {"image_id": image_id}
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
            rows.append(row)
        # Apply filters
        if filters:
            def match(row):
                for k, v in filters.items():
                    if row.get(k) != v:
                        return False
                return True
            filtered = [r for r in rows if match(r)]
        else:
            filtered = rows
        # Compute statistics
        statistics = {}
        if stats and 'field' in stats and 'operation' in stats:
            field = stats['field']
            op = stats['operation']
            values = [r[field] for r in filtered if field in r and r[field] is not None]
            if op == 'count':
                statistics['count'] = len(values)
            elif op == 'unique':
                statistics['unique'] = list(set(values))
            elif op == 'min':
                try:
                    statistics['min'] = min(values)
                except Exception:
                    statistics['min'] = None
            elif op == 'max':
                try:
                    statistics['max'] = max(values)
                except Exception:
                    statistics['max'] = None
        else:
            statistics['count'] = len(filtered)
        return json.dumps({
            "success": True,
            "filtered": filtered,
            "statistics": statistics
        })
