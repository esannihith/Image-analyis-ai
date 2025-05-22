import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
from datetime import datetime, timezone, timedelta
import math

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("TemporalTools", {}).get("SolarPositionAnalyzer", {}).get("config", {})
except Exception:
    tool_config = {}

class SolarPositionAnalyzerTool(BaseTool):
    name: str = "Solar Position Analyzer"
    description: str = (
        "Calculates the Sun's apparent position (azimuth and elevation) and identifies photographic lighting periods "
        "(e.g., golden hour, blue hour, daytime, nighttime) for a given UTC timestamp "
        "and geographic location (latitude, longitude, optional elevation). Uses a spherical earth model."
    )
    args_schema: Type[BaseModel] = SolarPositionInput

    # Configuration from YAML/env
    output_precision_config: int = tool_config.get("precision", int(os.getenv("SOLPOS_PRECISION", 2)))
    # Model config can be used if more algorithms are added later
    calculation_model_config: str = tool_config.get("model", os.getenv("SOLPOS_MODEL", "spherical_approx"))


    def _calculate_solar_position_spherical(
        self, 
        dt_utc: datetime, 
        lat_deg: float, 
        lon_deg: float,
        elevation_m: float = 0.0 # Elevation in meters for atmospheric refraction
    ) -> Dict[str, Any]:
        """
        Calculates solar position using a simplified spherical model.
        Reference: Simplified algorithm, e.g., based on NOAA's calculators or common astronomical formulas.
        This is an approximation. For very high accuracy, dedicated libraries like pvlib are recommended.
        """
        lat_rad = math.radians(lat_deg)
        lon_rad = math.radians(lon_deg)

        # 1. Julian Day and Time
        # Formula for Julian Day from datetime (standard astronomical formula)
        # Ensure datetime is naive UTC for these calculations
        year, month, day, hour, minute, sec = dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute, dt_utc.second
        if month <= 2:
            year -= 1
            month += 12
        
        A = math.floor(year / 100)
        B = 2 - A + math.floor(A / 4)
        JD = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5
        # Fractional part for time of day
        JD_time = (hour + minute / 60 + sec / 3600) / 24
        julian_day = JD + JD_time

        # Number of days since J2000.0 (January 1, 2000, 12:00 UT)
        n = julian_day - 2451545.0 

        # 2. Mean Solar Longitude (L) and Mean Anomaly (g) (degrees)
        L = (280.460 + 0.9856474 * n) % 360
        g_deg = (357.528 + 0.9856003 * n) % 360
        g_rad = math.radians(g_deg)

        # 3. Ecliptic Longitude (lambda) and Obliquity of the Ecliptic (epsilon) (degrees)
        lambda_lambda_deg = (L + 1.915 * math.sin(g_rad) + 0.020 * math.sin(2 * g_rad)) % 360
        lambda_rad = math.radians(lambda_deg)
        
        # Obliquity of the ecliptic (degrees) - simplified
        epsilon_deg = 23.439 - 0.0000004 * n 
        epsilon_rad = math.radians(epsilon_deg)

        # 4. Right Ascension (RA) and Declination (Dec)
        # RA (alpha)
        alpha_rad = math.atan2(math.cos(epsilon_rad) * math.sin(lambda_rad), math.cos(lambda_rad))
        # Declination (delta)
        delta_rad = math.asin(math.sin(epsilon_rad) * math.sin(lambda_rad))

        # 5. Local Sidereal Time (LST) / Hour Angle (H)
        # Greenwich Mean Sidereal Time (GMST) in degrees
        gmst_deg = (L + 180) % 360 # Approximation
        
        # Local Sidereal Time (LST) in degrees
        # lon_deg is positive for East, negative for West
        lst_deg = (gmst_deg + lon_deg) % 360
        
        # Hour Angle (H) in degrees, then radians
        # Hour Angle = LST - RA (Right Ascension in degrees)
        alpha_deg = math.degrees(alpha_rad)
        hour_angle_deg = (lst_deg - alpha_deg) % 360
        # Convert to range -180 to 180 for calculations if needed, or keep 0-360.
        # For cosine, it doesn't matter. For sign in azimuth, it can.
        # Let's adjust H to be between -180 and 180, where negative is East of meridian, positive is West
        if hour_angle_deg > 180:
            hour_angle_deg_corr = hour_angle_deg - 360
        else:
            hour_angle_deg_corr = hour_angle_deg
        
        H_rad = math.radians(hour_angle_deg_corr) # Corrected Hour Angle for azimuth convention

        # 6. Azimuth and Elevation (Altitude)
        # Elevation (alt_rad) / Altitude (a)
        sin_alt = math.sin(delta_rad) * math.sin(lat_rad) + math.cos(delta_rad) * math.cos(lat_rad) * math.cos(H_rad)
        alt_rad = math.asin(sin_alt)
        
        # Azimuth (az_rad)
        # Formula for Azimuth (measured from North, eastward)
        # Note: math.atan2(y, x)
        # cos_az = (math.sin(delta_rad) * math.cos(lat_rad) - math.cos(delta_rad) * math.sin(lat_rad) * math.cos(H_rad)) / math.cos(alt_rad)
        # sin_az = (math.cos(delta_rad) * math.sin(H_rad)) / math.cos(alt_rad)
        # az_rad = math.atan2(sin_az, cos_az) # This gives Az from South.
        
        # Azimuth from North, clockwise:
        y = -math.sin(H_rad)
        x = math.tan(delta_rad) * math.cos(lat_rad) - math.sin(lat_rad) * math.cos(H_rad)
        az_rad = math.atan2(y, x)

        az_deg = math.degrees(az_rad)
        alt_deg = math.degrees(alt_rad)

        # Azimuth from North (0 deg), East (90 deg), South (180 deg), West (270 deg)
        # The atan2(y,x) result is from -pi to pi. Convert to 0-360.
        # The formula used (atan2(-sin(H), tan(delta)cos(lat) - sin(lat)cos(H)))
        # should give Azimuth from South, positive West.
        # Let's use a more standard formula for Az from North, eastward:
        # H is hour angle, delta is declination, phi is latitude
        # sin(delta) = sin(phi)sin(alt) + cos(phi)cos(alt)cos(Az)
        # Az = acos( (sin(delta) - sin(phi)sin(alt)) / (cos(phi)cos(alt)) )
        # Sign of Azimuth depends on whether H is positive or negative (sin(H)).
        # If sin(H) < 0, Az = Az. Else Az = 360 - Az. (If Az from North)

        # Simpler Azimuth from North:
        az_numerator = -math.sin(H_rad)
        az_denominator = math.cos(lat_rad) * math.tan(delta_rad) - math.sin(lat_rad) * math.cos(H_rad)
        az_rad_north = math.atan2(az_numerator, az_denominator)
        
        az_deg_north = math.degrees(az_rad_north)
        # Convert atan2 result from (-pi, pi] to [0, 360)
        az_deg_final = (az_deg_north + 360) % 360


        # Atmospheric Refraction (simplified) - affects observed elevation
        # Only apply if alt_deg is above a certain threshold
        refraction_correction = 0.0 # degrees
        if alt_deg > -1: # Apply only if sun is near or above horizon
            # A simple formula for refraction at 10C and 1010mb pressure
            refraction_correction = (1.02 / math.tan(math.radians(alt_deg + 10.3 / (alt_deg + 5.11)))) / 60 # in degrees
        
        alt_deg_apparent = alt_deg + refraction_correction

        solar_zenith_deg = 90.0 - alt_deg_apparent

        return {
            "solar_azimuth_deg": round(az_deg_final, self.output_precision_config),
            "solar_elevation_deg": round(alt_deg_apparent, self.output_precision_config),
            "solar_zenith_deg": round(solar_zenith_deg, self.output_precision_config),
            "apparent_elevation_deg": round(alt_deg_apparent, self.output_precision_config),
            "calculated_elevation_deg_no_refraction": round(alt_deg, self.output_precision_config),
            "refraction_correction_deg": round(refraction_correction, self.output_precision_config+2), # more precision for correction itself
            "calculation_model_used": "spherical_approx_v1"
        }

    def _run(self, utc_timestamp_iso: str, latitude: float, longitude: float, elevation_m: Optional[float] = 0.0) -> str:
        response: Dict[str, Any] = {"success": False}

        try:
            # Parse UTC timestamp
            # Ensure it's a 'Z' terminated or offset-to-zero string for proper UTC parsing
            if not utc_timestamp_iso.endswith('Z') and '+' not in utc_timestamp_iso[10:] and '-' not in utc_timestamp_iso[10:]:
                 # If no 'Z' and no offset part, assume it's naive but meant to be UTC.
                 # However, standard ISO8601 for UTC should have Z.
                 # For robustness, we might append 'Z' if it looks like a naive local time string intended as UTC.
                 # Best practice is for the input to be correctly formatted.
                 # dt_utc = datetime.fromisoformat(utc_timestamp_iso.replace('Z', '') + '+00:00')
                 dt_utc = datetime.fromisoformat(utc_timestamp_iso).replace(tzinfo=timezone.utc) # if truly naive and known UTC
            else:
                dt_utc = datetime.fromisoformat(utc_timestamp_iso.replace('Z', '+00:00'))

            # Ensure it's UTC and naive for calculations (some formulas expect naive UTC)
            if dt_utc.tzinfo is None: # Should not happen if fromisoformat worked with Z or offset
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            else:
                dt_utc = dt_utc.astimezone(timezone.utc)
            
            # Remove tzinfo to make it naive UTC for the spherical algorithm, as it recalculates based on Julian day.
            dt_utc_naive = dt_utc.replace(tzinfo=None)

        except ValueError:
            response["error"] = f"Invalid UTC timestamp format: '{utc_timestamp_iso}'. Please use ISO8601 format (e.g., YYYY-MM-DDTHH:MM:SSZ or with UTC offset)."
            return json.dumps(response)

        if not (-90 <= latitude <= 90):
            response["error"] = f"Invalid latitude: {latitude}. Must be between -90 and 90."
            return json.dumps(response)
        if not (-180 <= longitude <= 180):
            response["error"] = f"Invalid longitude: {longitude}. Must be between -180 and 180."
            return json.dumps(response)

        try:
            if self.calculation_model_config.startswith("spherical"):
                solar_position_data = self._calculate_solar_position_spherical(
                    dt_utc_naive, latitude, longitude, elevation_m if elevation_m is not None else 0.0
                )
            else:
                response["error"] = f"Unsupported solar position model: {self.calculation_model_config}"
                return json.dumps(response)

            response.update({
                "success": True,
                "input_utc_timestamp": utc_timestamp_iso,
                "input_latitude": latitude,
                "input_longitude": longitude,
                "input_elevation_m": elevation_m,
                **solar_position_data
            })

        except Exception as e:
            response["success"] = False
            response["error"] = f"Error during solar position calculation: {str(e)}"
            # In a real app, log the full stack trace here
            # logger.error(f"Solar position calculation failed: {e}", exc_info=True)
            
        return json.dumps(response, default=str)
