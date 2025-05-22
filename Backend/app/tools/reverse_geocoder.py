import yaml
from pathlib import Path
import os
from typing import Type, Optional, Dict, List, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import requests
import json

# Load configuration from tools.yaml or environment variables
try:
    with open(Path("app/config/tools.yaml")) as f:
        config = yaml.safe_load(f)["GeospatialTools"]["ReverseGeocoder"]
except:
    config = {}

# ----------------------------
# Input schema for validation
# ----------------------------
class ReverseGeocoderInput(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")

# ----------------------------
# ReverseGeocoder Tool Class
# ----------------------------
class ReverseGeocoderTool(BaseTool):
    name: str = "Reverse Geocoder"
    description: str = "Converts GPS coordinates (latitude, longitude) into a structured JSON with address data."
    args_schema: Type[BaseModel] = ReverseGeocoderInput

    # Config values from YAML or env variables
    provider: str = config.get("provider", os.getenv("GEOCODING_PROVIDER", "nominatim"))
    api_key: Optional[str] = config.get("api_key", os.getenv("GEOCODING_API_KEY"))
    fallback_providers: list = config.get("fallback_providers", ["nominatim"])

    def _run(self, lat: float, lon: float) -> str:
        result = {
            "coordinates": [lat, lon],
            "address": {},
            "landmarks": []  # Empty array, to be populated by LandmarkMatcher
        }
        
        try:
            if self.provider == "google" and self.api_key:
                result["address"] = self._query_google(lat, lon)
            else:
                result["address"] = self._query_nominatim(lat, lon)
        except Exception as e:
            success = False
            for fallback in self.fallback_providers:
                try:
                    if fallback == "nominatim":
                        result["address"] = self._query_nominatim(lat, lon)
                        success = True
                        break
                except:
                    continue
            
            if not success:
                result["address"] = {"error": f"Error during reverse geocoding: {str(e)}"}
        
        return json.dumps(result)

    def _query_google(self, lat: float, lon: float) -> Dict[str, Any]:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={self.api_key}"
        resp = requests.get(url)
        data = resp.json()
        
        if data.get("status") == "OK" and data.get("results"):
            result = data["results"][0]
            address_components = {}
            
            # Extract address components
            for component in result.get("address_components", []):
                for component_type in component.get("types", []):
                    address_components[component_type] = component.get("long_name")
            
            return {
                "full_address": result.get("formatted_address", ""),
                "components": address_components,
                "place_id": result.get("place_id", ""),
                "provider": "google"
            }
        return {"full_address": "No address found via Google.", "provider": "google"}

    def _query_nominatim(self, lat: float, lon: float) -> Dict[str, Any]:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 18,
            "addressdetails": 1
        }
        headers = {"User-Agent": "CrewAI-Agent"}
        resp = requests.get(url, params=params, headers=headers)
        data = resp.json()
        
        if data:
            return {
                "full_address": data.get("display_name", ""),
                "components": data.get("address", {}),
                "osm_id": data.get("osm_id", ""),
                "osm_type": data.get("osm_type", ""),
                "provider": "nominatim"
            }
        return {"full_address": "No address found via Nominatim.", "provider": "nominatim"}
