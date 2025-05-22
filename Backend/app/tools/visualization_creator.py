import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import re

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
            tool_config = full_config.get("ResponseTools", {}).get("VisualizationCreator", {}).get("config", {})
    else:
        tool_config = {}
except Exception as e:
    print(f"Error loading VisualizationCreator config: {e}")
    tool_config = {}

DEFAULT_ALLOWED_FORMATS = ["table", "bar_chart", "line_chart", "map", "timeline", "text_summary"]
DEFAULT_MAX_SUGGESTIONS = 2
DEFAULT_KEYWORDS_FOR_MAP = ["location", "gps", "latitude", "longitude", "address", "place", "coordinates"]
DEFAULT_KEYWORDS_FOR_TIMELINE = ["timestamp", "date", "event", "sequence", "history", "chronology"]
DEFAULT_KEYWORDS_FOR_CHART = [
    "compare", "trend", "distribution", "value", "amount", "count", "percentage", 
    "iso", "aperture", "shutter_speed", "focal_length", "measurement", "statistic"
]

class VisualizationCreatorInput(BaseModel):
    """Input schema for VisualizationCreatorTool."""
    data_context: Union[Dict[str, Any], List[Dict[str, Any]], str] = Field(..., description="The data or text context for which visualization suggestions are needed. Can be a dictionary, list of dictionaries (e.g. from MatrixComparator), or a descriptive string.")
    max_suggestions_override: Optional[int] = Field(None, description="Optional: Override the maximum number of suggestions from config.")

class VisualizationCreatorTool(BaseTool):
    name: str = "Visualization Suggester"
    description: str = (
        "Suggests suitable visualization types based on the input data context or textual description. "
        "Helps in deciding how to best present information to the user."
    )
    args_schema: Type[BaseModel] = VisualizationCreatorInput

    _allowed_formats: List[str]
    _max_suggestions: int
    _keywords_map: Dict[str, List[str]]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._allowed_formats = tool_config.get("allowed_formats", DEFAULT_ALLOWED_FORMATS)
        self._max_suggestions = tool_config.get("max_suggestions", DEFAULT_MAX_SUGGESTIONS)
        
        # Consolidate keyword lists for easier processing
        self._keywords_map = {
            "map": tool_config.get("keywords_for_map", DEFAULT_KEYWORDS_FOR_MAP),
            "timeline": tool_config.get("keywords_for_timeline", DEFAULT_KEYWORDS_FOR_TIMELINE),
            "bar_chart": tool_config.get("keywords_for_chart", DEFAULT_KEYWORDS_FOR_CHART), # bar_chart uses general chart keywords
            "line_chart": tool_config.get("keywords_for_chart", DEFAULT_KEYWORDS_FOR_CHART), # line_chart also uses general chart keywords
        }
        # 'table' and 'text_summary' are often default or fallback suggestions.

    def _analyze_data_structure(self, data: Any) -> List[str]:
        """Analyzes the structure of the data to infer visualization types."""
        suggestions = []
        if isinstance(data, list) and data:
            if all(isinstance(item, dict) for item in data):
                # List of dictionaries often implies tabular data or items to be plotted
                suggestions.append("table")
                # If dicts have common numeric keys, could be chartable
                # For simplicity, we'll let keyword analysis handle chart types more directly for now
                if len(data) > 1 and len(data[0].keys()) > 2 : # more than just id and one value
                     if any(isinstance(data[0].get(k), (int, float)) for k in data[0].keys() if k != 'image_id' and k != 'id'):
                        suggestions.append("bar_chart") # Good for comparing items
                        if "timestamp" in data[0] or "date" in data[0]: # If items have time, line chart might be good
                            suggestions.append("line_chart")


        elif isinstance(data, dict):
            # A single dictionary might be a summary, or could represent series for a chart
            if "comparison_matrix" in data and isinstance(data["comparison_matrix"], list): # Output from MatrixComparator
                suggestions.append("table")
                if len(data["comparison_matrix"]) > 0 and len(data["comparison_matrix"][0]) > 3: # More than id and a couple of fields
                    suggestions.append("bar_chart") # Compare items in matrix
            if "image_scores" in data: # Also from MatrixComparator
                suggestions.append("table") # Scores can be tabular

        return list(set(suggestions)) # Unique suggestions

    def _analyze_text_keywords(self, text_content: str) -> List[str]:
        """Analyzes text for keywords to suggest visualization types."""
        suggestions = []
        text_lower = text_content.lower()
        
        for viz_type, keywords in self._keywords_map.items():
            if any(re.search(r'\b' + keyword + r'\b', text_lower) for keyword in keywords):
                suggestions.append(viz_type)
        
        return list(set(suggestions))

    def _run(
        self,
        data_context: Union[Dict[str, Any], List[Dict[str, Any]], str],
        max_suggestions_override: Optional[int] = None
    ) -> str:
        logs: List[str] = ["VisualizationCreatorTool started."]
        suggestions: List[str] = []

        current_max_suggestions = max_suggestions_override if max_suggestions_override is not None else self._max_suggestions

        if isinstance(data_context, str):
            logs.append(f"Analyzing string data_context: '{data_context[:100]}...'")
            suggestions.extend(self._analyze_text_keywords(data_context))
        elif isinstance(data_context, (dict, list)):
            logs.append(f"Analyzing structured data_context (type: {type(data_context).__name__}).")
            suggestions.extend(self._analyze_data_structure(data_context))
            # Also analyze string representation of structured data for keywords
            try:
                # Convert dict/list to string for keyword analysis as a fallback/enhancement
                stringified_data = json.dumps(data_context, default=str)
                suggestions.extend(self._analyze_text_keywords(stringified_data))
            except Exception as e:
                logs.append(f"Could not stringify structured data for keyword analysis: {e}")
        else:
            logs.append(f"Unsupported data_context type: {type(data_context).__name__}.")
            return json.dumps({"success": False, "suggestions": [], "error": "Unsupported data_context type.", "logs": logs})

        # Ensure suggestions are unique and from allowed formats
        unique_suggestions = []
        for s in suggestions:
            if s not in unique_suggestions and s in self._allowed_formats:
                unique_suggestions.append(s)
        
        # Prioritize more specific visualizations over generic ones if too many
        # For now, simple truncation. Could add priority logic later.
        final_suggestions = unique_suggestions[:current_max_suggestions]

        # Ensure "text_summary" or "table" is an option if no other specific viz fits or list is short
        if not final_suggestions and "text_summary" in self._allowed_formats:
            final_suggestions.append("text_summary")
        elif len(final_suggestions) == 1 and final_suggestions[0] != "table" and "table" in self._allowed_formats and isinstance(data_context, (list, dict)):
             # If only one non-table suggestion for structured data, add table as an alternative
            if len(final_suggestions) < current_max_suggestions:
                final_suggestions.append("table")


        logs.append(f"Final suggestions: {final_suggestions}")
        return json.dumps({"success": True, "suggestions": final_suggestions, "logs": logs}) 