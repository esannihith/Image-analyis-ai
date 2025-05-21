from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import requests
import json
import os
from datetime import datetime

class WeatherDataInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    image_id: str = Field(..., description="Image ID for which to fetch weather data.")

class WeatherDataTool(BaseTool):
    name: str = "Weather Data Tool"
    description: str = (
        "Fetches timestamp and GPS data from cached image metadata and uses the Visual Crossing Weather API "
        "to return weather conditions (temperature, cloud cover, rainfall, etc.) at the time and place the image was taken."
    )
    args_schema: Type[BaseModel] = WeatherDataInput

    def _run(self, session_id: str, image_id: str) -> str:
        store = SessionStore()
        metadata = store.get_metadata(session_id, image_id)
        if not metadata:
            return json.dumps({"success": False, "error": f"No metadata found for image {image_id} in session {session_id}."})
        # Extract timestamp and GPS info
        ts = None
        gps = None
        if 'processed_data' in metadata:
            ts = metadata['processed_data']['datetime_info'].get('date_time_original')
            gps = metadata['processed_data']['gps_info']
        if not ts or not gps or not gps.get('latitude') or not gps.get('longitude'):
            return json.dumps({"success": False, "error": "Missing timestamp or GPS data in image metadata."})
        # Convert timestamp to ISO8601 date
        try:
            # EXIF date format: 'YYYY:MM:DD HH:MM:SS'
            dt = datetime.strptime(ts.split()[0], '%Y:%m:%d')
            date_str = dt.strftime('%Y-%m-%d')
        except Exception:
            date_str = ts.split()[0].replace(':', '-')  # fallback
        # Convert GPS DMS to decimal
        def dms_to_decimal(dms, ref):
            if isinstance(dms, str):
                try:
                    parts = [float(x) for x in dms.replace('[','').replace(']','').split(',')]
                    if len(parts) == 3:
                        deg, minutes, seconds = parts
                        dec = deg + minutes/60 + seconds/3600
                        if ref in ['S', 'W']:
                            dec = -dec
                        return dec
                except Exception:
                    return None
            elif isinstance(dms, (list, tuple)) and len(dms) == 3:
                deg, minutes, seconds = dms
                dec = deg + minutes/60 + seconds/3600
                if ref in ['S', 'W']:
                    dec = -dec
                return dec
            return None
        lat = dms_to_decimal(gps.get('latitude'), gps.get('latitude_ref'))
        lon = dms_to_decimal(gps.get('longitude'), gps.get('longitude_ref'))
        if lat is None or lon is None:
            return json.dumps({"success": False, "error": "Failed to parse GPS coordinates."})
        # Query Visual Crossing Weather API
        api_key = os.getenv('VISUAL_CROSSING_API_KEY')
        if not api_key:
            return json.dumps({"success": False, "error": "No Visual Crossing API key found in environment."})
        try:
            url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/{date_str}?unitGroup=metric&key={api_key}&include=days&elements=datetime,tempmax,tempmin,temp,precip,preciptype,humidity,cloudcover,conditions,description,icon"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if 'days' in data and data['days']:
                day = data['days'][0]
                return json.dumps({
                    "success": True,
                    "weather": day,
                    "location": {"lat": lat, "lon": lon},
                    "date": date_str,
                    "provider": "visualcrossing"
                })
            else:
                return json.dumps({"success": False, "error": f"No weather data found for {date_str} at {lat},{lon}."})
        except Exception as e:
            return json.dumps({"success": False, "error": f"Weather API request failed: {e}"})
