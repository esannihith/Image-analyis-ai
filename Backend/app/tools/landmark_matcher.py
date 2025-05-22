import yaml
from pathlib import Path
import os
import json
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import requests

# Load configuration from tools.yaml or use environment variables as fallback
try:
    with open(Path("app/config/tools.yaml")) as f:
        config = yaml.safe_load(f)["GeospatialTools"]["LandmarkMatcher"]
except:
    config = {}

# ------------------------------
# Input schema for the tool
# ------------------------------
class LandmarkMatcherInput(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")

# ------------------------------
# LandmarkMatcher Tool Class
# ------------------------------
class LandmarkMatcher(BaseTool):
    name: str = "Landmark Matcher"
    description: str = "Identifies nearby well-known landmarks within a certain radius, returning JSON data."
    args_schema: Type[BaseModel] = LandmarkMatcherInput

    # Config fields from config or environment variables
    database_source: str = config.get("database", os.getenv("LANDMARK_DATABASE", "wikidata"))
    search_radius: int = int(config.get("search_radius", os.getenv("LANDMARK_SEARCH_RADIUS", 5000)))  # in meters

    def _run(self, lat: float, lon: float) -> str:
        result = {
            "coordinates": [lat, lon],
            "landmarks": [],
            "search_radius_meters": self.search_radius
        }
        
        try:
            if self.database_source == "wikidata":
                result["landmarks"] = self._query_wikidata(lat, lon)
                result["source"] = "wikidata"
            else:
                result["error"] = f"Unsupported landmark database: {self.database_source}"
        except Exception as e:
            result["error"] = f"Error querying landmarks: {str(e)}"
        
        return json.dumps(result)

    def _query_wikidata(self, lat: float, lon: float) -> List[str]:
        query = f'''
        SELECT ?placeLabel WHERE {{
          ?place wdt:P31/wdt:P279* wd:Q839954 .
          ?place wdt:P625 ?location .
          SERVICE wikibase:around {{
            ?place wdt:P625 ?location .
            bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
            bd:serviceParam wikibase:radius "{self.search_radius / 1000}" .
          }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        '''

        url = "https://query.wikidata.org/sparql"
        headers = {"Accept": "application/sparql-results+json"}
        response = requests.get(url, params={"query": query}, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Wikidata query failed with status {response.status_code}")

        data = response.json()
        return [b["placeLabel"]["value"] for b in data["results"]["bindings"]]
