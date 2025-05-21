from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from app.store.session_store import SessionStore
import csv
import io
import json
import os

"""
CSV export tool for CrewAI. Serializes all session metadata into CSV format and provides a download link.
Returns output matching the standardized schema: {"download_link": <str>, "csv": <str>, "success": <bool>, "error": <str|null>}.
"""

class CSVExportInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")

class CSVExportTool(BaseTool):
    name: str = "CSV Export Tool"
    description: str = (
        "Serializes all metadata cached under a session into CSV format and provides a download link."
    )
    args_schema: Type[BaseModel] = CSVExportInput

    def _run(self, session_id: str) -> str:
        """
        Export session metadata to CSV. Returns standardized output.
        """
        try:
            store = SessionStore()
            all_metadata = store.get_all_metadata(session_id)
            if not all_metadata:
                return json.dumps({
                    "download_link": "",
                    "csv": "",
                    "success": False,
                    "error": f"No metadata found for session {session_id}."
                })
            # Flatten metadata for CSV
            rows = []
            fieldnames = set()
            for image_id, meta in all_metadata.items():
                row = {"image_id": image_id}
                # Flatten processed_data if present
                if 'processed_data' in meta:
                    for section, section_data in meta['processed_data'].items():
                        if isinstance(section_data, dict):
                            for k, v in section_data.items():
                                row[f"{section}_{k}"] = v
                        else:
                            row[section] = section_data
                # Add top-level fields
                for k, v in meta.items():
                    if k != 'processed_data':
                        row[k] = v
                fieldnames.update(row.keys())
                rows.append(row)
            fieldnames = sorted(fieldnames)
            # Write CSV to memory
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            csv_data = output.getvalue()
            output.close()
            # For now, download_link is empty (to be set by backend route)
            return json.dumps({
                "download_link": "",
                "csv": csv_data,
                "success": True,
                "error": None
            })
        except Exception as e:
            return json.dumps({
                "download_link": "",
                "csv": "",
                "success": False,
                "error": str(e)
            })
