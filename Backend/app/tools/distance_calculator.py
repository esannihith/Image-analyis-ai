import yaml
from pathlib import Path
import os
import json
from typing import Type, List, Tuple, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from geopy.distance import geodesic

# Load configuration from tools.yaml or environment variables
try:
    with open(Path("app/config/tools.yaml")) as f:
        config = yaml.safe_load(f)["GeospatialTools"]["DistanceCalculator"]
except:
    config = {}

# ------------------------------
# Input schema for validation
# ------------------------------
class DistanceCalculatorInput(BaseModel):
    coordinates: List[Tuple[float, float]] = Field(
        ..., 
        description="List of latitude/longitude tuples. Must include at least two locations."
    )

# ------------------------------
# DistanceCalculator Tool Class
# ------------------------------
class DistanceCalculator(BaseTool):
    name: str = "Distance Calculator"
    description: str = "Calculates distance between multiple image coordinates using Haversine/geodesic formula."
    args_schema: Type[BaseModel] = DistanceCalculatorInput

    unit_system: str = config.get("unit_system", os.getenv("DISTANCE_UNIT_SYSTEM", "metric"))  # metric or imperial
    precision: int = int(config.get("precision", os.getenv("DISTANCE_PRECISION", 2)))

    def _run(self, coordinates: List[Tuple[float, float]]) -> str:
        result = {
            "coordinates": coordinates,
            "unit_system": self.unit_system,
            "distances": [],
            "total_distance": 0,
            "success": True
        }
        
        if len(coordinates) < 2:
            result["success"] = False
            result["error"] = "At least two coordinates are required."
            return json.dumps(result)

        total_distance = 0
        for i in range(len(coordinates) - 1):
            point1 = coordinates[i]
            point2 = coordinates[i + 1]
            
            try:
                dist_km = geodesic(point1, point2).kilometers
                distance = round(dist_km if self.unit_system == "metric" else dist_km * 0.621371, self.precision)
                total_distance += distance
                
                distance_obj = {
                    "from": list(point1),
                    "to": list(point2),
                    "distance": distance,
                    "unit": "km" if self.unit_system == "metric" else "miles"
                }
                
                result["distances"].append(distance_obj)
            except Exception as e:
                result["distances"].append({
                    "from": list(point1),
                    "to": list(point2),
                    "error": str(e)
                })
        
        result["total_distance"] = round(total_distance, self.precision)
        result["total_unit"] = "km" if self.unit_system == "metric" else "miles"
        
        return json.dumps(result)