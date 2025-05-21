from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from image_metadata_conversational_assistant.store.session_store import SessionStore
import requests
import json
import os

class ReverseGeocodeInput(BaseModel):
    session_id: str = Field(..., description="Session ID for the user session.")
    image_id: str = Field(..., description="Image ID for which to reverse geocode location.")

class ReverseGeocodingTool(BaseTool):
    name: str = "Reverse Geocoding Tool"
    description: str = (
        "Fetches GPS data from cached image metadata and uses a geocoding API (Google Maps or OpenStreetMap) "
        "to return a human-friendly location string."
    )
    args_schema: Type[BaseModel] = ReverseGeocodeInput

    def _run(self, session_id: str, image_id: str) -> str:
        store = SessionStore()
        metadata = store.get_metadata(session_id, image_id)
        if not metadata:
            return json.dumps({"success": False, "error": f"No metadata found for image {image_id} in session {session_id}."})
        # Try to extract GPS info from processed_data or exif
        gps = None
        if 'processed_data' in metadata and 'gps_info' in metadata['processed_data']:
            gps = metadata['processed_data']['gps_info']
        elif 'exif' in metadata:
            gps = {
                'latitude': metadata['exif'].get('Exif.GPSInfo.GPSLatitude', ''),
                'latitude_ref': metadata['exif'].get('Exif.GPSInfo.GPSLatitudeRef', ''),
                'longitude': metadata['exif'].get('Exif.GPSInfo.GPSLongitude', ''),
                'longitude_ref': metadata['exif'].get('Exif.GPSInfo.GPSLongitudeRef', '')
            }
        if not gps or not gps.get('latitude') or not gps.get('longitude'):
            return json.dumps({"success": False, "error": "No GPS data found in image metadata."})
        # Convert GPS DMS to decimal if needed
        def dms_to_decimal(dms, ref):
            if isinstance(dms, str):
                # Try to parse as 'deg, min, sec' string
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
        # Try Google Maps API first if key is present
        google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if google_api_key:
            try:
                url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={google_api_key}"
                resp = requests.get(url, timeout=10)
                data = resp.json()
                if data.get('status') == 'OK' and data.get('results'):
                    address = data['results'][0]['formatted_address']
                    return json.dumps({"success": True, "location": address, "provider": "google"})
            except Exception as e:
                pass  # fallback to OSM
        # Fallback to OpenStreetMap Nominatim
        try:
            url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=16&addressdetails=1"
            headers = {"User-Agent": "ImageMetadataConversationalAssistant/1.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            if 'display_name' in data:
                return json.dumps({"success": True, "location": data['display_name'], "provider": "osm"})
            else:
                return json.dumps({"success": False, "error": "No location found from OSM."})
        except Exception as e:
            return json.dumps({"success": False, "error": f"Reverse geocoding failed: {e}"})
