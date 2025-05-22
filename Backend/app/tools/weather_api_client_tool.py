import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import urllib.request
import urllib.parse
from datetime import datetime

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
            tool_config = full_config.get("EnvironmentalTools", {}).get("WeatherAPIClientTool", {}).get("config", {})
    else:
        tool_config = {}
except Exception as e:
    print(f"Error loading WeatherAPIClientTool config: {e}")
    tool_config = {}

DEFAULT_ELEMENTS = [
    "datetime", "tempmax", "tempmin", "temp", "feelslike", "humidity", "precip", 
    "windspeed", "winddir", "pressure", "cloudcover", "visibility", 
    "sunrise", "sunset", "conditions", "description"
]
DEFAULT_UNIT_GROUP = "metric"
DEFAULT_BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"

class WeatherAPIClientInput(BaseModel):
    """Input schema for WeatherAPIClientTool."""
    latitude: float = Field(..., description="Latitude of the location.")
    longitude: float = Field(..., description="Longitude of the location.")
    date: str = Field(..., description="Date for the weather query in YYYY-MM-DD format.")
    api_key_override: Optional[str] = Field(None, description="Optional: Override API key from config.")
    elements_override: Optional[List[str]] = Field(None, description="Optional: List of specific weather elements to fetch.")
    unit_group_override: Optional[str] = Field(None, description="Optional: Unit group (e.g., 'metric', 'us'). Overrides config.")

class WeatherAPIClientTool(BaseTool):
    name: str = "Historical Weather Fetcher"
    description: str = (
        "Fetches historical daily weather data for a specific latitude, longitude, and date "
        "using the Visual Crossing Weather API."
    )
    args_schema: Type[BaseModel] = WeatherAPIClientInput

    _api_key: str
    _base_url: str
    _default_elements: List[str]
    _default_unit_group: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._api_key = os.getenv("VISUAL_CROSSING_API_KEY", tool_config.get("api_key"))
        self._base_url = tool_config.get("base_url", DEFAULT_BASE_URL)
        self._default_elements = tool_config.get("default_elements", DEFAULT_ELEMENTS)
        self._default_unit_group = tool_config.get("default_unit_group", DEFAULT_UNIT_GROUP)

        if not self._api_key:
            print("Warning: VISUAL_CROSSING_API_KEY not found in environment or config for WeatherAPIClientTool.")
            # The tool will likely fail without an API key.

    def _run(
        self,
        latitude: float,
        longitude: float,
        date: str, # Expects YYYY-MM-DD
        api_key_override: Optional[str] = None,
        elements_override: Optional[List[str]] = None,
        unit_group_override: Optional[str] = None
    ) -> str:
        logs: List[str] = []
        
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps({"success": False, "error": "Invalid date format. Please use YYYY-MM-DD.", "data": None, "logs": logs})

        current_api_key = api_key_override if api_key_override else self._api_key
        if not current_api_key:
            return json.dumps({"success": False, "error": "API key for Visual Crossing is missing.", "data": None, "logs": logs})

        elements_to_fetch = elements_override if elements_override else self._default_elements
        unit_group = unit_group_override if unit_group_override else self._default_unit_group
        
        location_str = f"{latitude},{longitude}"
        # For a single day, the API uses the date as both start and end date in the path
        # or just the single date if only one is provided.
        # The API expects date in YYYY-MM-DD format.
        request_url_path = f"{location_str}/{date}"

        params = {
            "key": current_api_key,
            "unitGroup": unit_group,
            "include": "days", # We want daily summaries
            "elements": ",".join(elements_to_fetch)
        }
        
        query_string = urllib.parse.urlencode(params)
        full_url = f"{self._base_url}{request_url_path}?{query_string}"
        logs.append(f"Requesting weather data from: {self._base_url}{request_url_path}?key=REDACTED&...") # Log URL without key

        try:
            with urllib.request.urlopen(full_url, timeout=10) as response:
                response_content = response.read()
                if response.status != 200:
                    logs.append(f"API Error: Status {response.status}, Body: {response_content.decode('utf-8', 'ignore')[:500]}")
                    return json.dumps({"success": False, "error": f"Visual Crossing API request failed with status {response.status}.", "details": response_content.decode('utf-8', 'ignore')[:500], "data": None, "logs": logs})
                
                weather_data_json = json.loads(response_content.decode('utf-8'))
                
                # Extract data for the specific day.
                # Visual Crossing returns a 'days' array. For a single date query, it should contain one entry.
                if "days" in weather_data_json and isinstance(weather_data_json["days"], list) and len(weather_data_json["days"]) > 0:
                    daily_data = weather_data_json["days"][0] # Assuming the first day entry is the one we want for the queried date
                    
                    # Filter to only include requested elements if API returns more
                    filtered_daily_data = {key: daily_data.get(key) for key in elements_to_fetch if key in daily_data}
                    
                    logs.append(f"Successfully fetched and parsed weather data for {date} at {location_str}.")
                    return json.dumps({"success": True, "data": filtered_daily_data, "logs": logs}, default=str)
                else:
                    logs.append(f"No 'days' data found in API response or 'days' array is empty. Response: {weather_data_json}")
                    return json.dumps({"success": False, "error": "Weather data for the specified date not found in API response.", "data": None, "logs": logs})

        except urllib.error.URLError as e:
            logs.append(f"Network error (URLError) when calling Visual Crossing API: {e.reason}")
            return json.dumps({"success": False, "error": f"Network error accessing weather API: {e.reason}", "data": None, "logs": logs})
        except json.JSONDecodeError as e:
            logs.append(f"Failed to decode JSON response from Visual Crossing API: {e}")
            return json.dumps({"success": False, "error": "Invalid JSON response from weather API.", "data": None, "logs": logs})
        except Exception as e:
            logs.append(f"Unexpected error in WeatherAPIClientTool: {type(e).__name__} - {e}")
            import traceback
            logs.append(traceback.format_exc(limit=3))
            return json.dumps({"success": False, "error": f"An unexpected error occurred: {e}", "data": None, "logs": logs})
