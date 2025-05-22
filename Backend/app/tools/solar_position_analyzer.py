import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from crewai.tools import BaseTool
import json
from datetime import datetime, timezone, timedelta
import math
import logging # Added for logging

# Configure a logger for this tool
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# Base model for tool inputs
class BaseToolInput(BaseModel):
    """Base model for all tool input schemas."""
    pass

# Input schema for SolarPositionAnalyzerTool
class SolarPositionInput(BaseToolInput):
    """Input schema for the Solar Position Analyzer Tool."""
    latitude: float = Field(..., description="Latitude in decimal degrees.")
    longitude: float = Field(..., description="Longitude in decimal degrees.")
    utc_timestamp_iso: str = Field(
        ...,
        description="UTC timestamp in ISO 8601 format (e.g., YYYY-MM-DDTHH:MM:SSZ or with UTC offset).",
        examples=["2023-10-26T10:30:00Z", "2024-01-15T18:45:30+05:30"]
    )
    elevation_m: Optional[float] = Field(
        default=0.0,
        description="Observer's elevation above sea level in meters. Defaults to 0.0m."
    )

    @validator('latitude')
    def latitude_must_be_valid(cls, v):
        if not (-90 <= v <= 90):
            raise ValueError('Latitude must be between -90 and 90 degrees.')
        return v

    @validator('longitude')
    def longitude_must_be_valid(cls, v):
        if not (-180 <= v <= 180):
            raise ValueError('Longitude must be between -180 and 180 degrees.')
        return v

    @validator('utc_timestamp_iso')
    def timestamp_must_be_valid_iso(cls, v):
        try:
            # Attempt to parse with timezone awareness
            if 'Z' in v or '+' in v or (len(v) > 10 and '-' in v[10:]): # Check for explicit offset or Z
                 datetime.fromisoformat(v.replace('Z', '+00:00'))
            else:
                # If no Z or offset, try parsing as naive.
                # The tool's _run method handles final UTC conversion logic.
                datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid ISO 8601 timestamp format: '{v}'")
        return v


# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("TemporalTools", {}).get("SolarPositionAnalyzer", {}).get("config", {})
except Exception as e:
    logger.warning(f"Could not load tools.yaml for SolarPositionAnalyzerTool: {e}")
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
        year, month, day, hour, minute, sec = dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute, dt_utc.second
        if month <= 2:
            year -= 1
            month += 12

        A = math.floor(year / 100)
        B = 2 - A + math.floor(A / 4)
        JD = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5
        JD_time = (hour + minute / 60 + sec / 3600) / 24
        julian_day = JD + JD_time

        n = julian_day - 2451545.0

        # 2. Mean Solar Longitude (L) and Mean Anomaly (g) (degrees)
        L = (280.460 + 0.9856474 * n) % 360
        g_deg = (357.528 + 0.9856003 * n) % 360
        g_rad = math.radians(g_deg)

        # 3. Ecliptic Longitude (lambda_ecl_deg) and Obliquity of the Ecliptic (epsilon_deg) (degrees)
        lambda_ecl_deg = (L + 1.915 * math.sin(g_rad) + 0.020 * math.sin(2 * g_rad)) % 360
        lambda_ecl_rad = math.radians(lambda_ecl_deg)

        epsilon_deg = 23.439 - 0.0000004 * n
        epsilon_rad = math.radians(epsilon_deg)

        # 4. Right Ascension (RA) and Declination (Dec)
        alpha_rad = math.atan2(math.cos(epsilon_rad) * math.sin(lambda_ecl_rad), math.cos(lambda_ecl_rad))
        delta_rad = math.asin(math.sin(epsilon_rad) * math.sin(lambda_ecl_rad))

        # 5. Local Sidereal Time (LST) / Hour Angle (H)
        gmst_hours = (18.697374558 + 24.06570982441908 * n) % 24 # GMST in hours
        gmst_deg = gmst_hours * 15 # GMST in degrees
        
        lst_deg = (gmst_deg + lon_deg) % 360
        
        alpha_deg = math.degrees(alpha_rad)
        hour_angle_deg = (lst_deg - alpha_deg) 

        # Adjust H to be between -180 and 180
        if hour_angle_deg > 180:
            hour_angle_deg_corr = hour_angle_deg - 360
        elif hour_angle_deg < -180:
             hour_angle_deg_corr = hour_angle_deg + 360
        else:
            hour_angle_deg_corr = hour_angle_deg
        
        H_rad = math.radians(hour_angle_deg_corr)

        # 6. Azimuth and Elevation (Altitude)
        sin_alt = math.sin(delta_rad) * math.sin(lat_rad) + math.cos(delta_rad) * math.cos(lat_rad) * math.cos(H_rad)
        alt_rad = math.asin(sin_alt)
        alt_deg = math.degrees(alt_rad)

        # Azimuth from North, clockwise:
        az_numerator = -math.sin(H_rad)
        az_denominator = (math.cos(delta_rad) * math.sin(lat_rad) - math.sin(delta_rad) * math.cos(lat_rad) * math.cos(H_rad))
        # Protect against division by zero if denominator is very close to zero (e.g. at poles or when alt_rad is close to +/- pi/2)
        if abs(math.cos(alt_rad)) < 1e-9 : # if sun is at zenith/nadir
             az_rad_north = 0 # Azimuth is undefined/irrelevant
        else:
             az_rad_north = math.atan2(az_numerator * math.cos(delta_rad), az_denominator)


        az_deg_north = math.degrees(az_rad_north)
        az_deg_final = (az_deg_north + 360) % 360 # Convert atan2 result from (-pi, pi] to [0, 360)


        # Atmospheric Refraction (simplified) - affects observed elevation
        refraction_correction = 0.0 # degrees
        # More robust formula for refraction (Bennett, 1982), valid for alt_deg > -5 deg
        if alt_deg > -5:
            alt_deg_for_refraction = alt_deg # Use geometric altitude
            refraction_correction_arcmin = 1.0 / math.tan(math.radians(alt_deg_for_refraction + 7.31 / (alt_deg_for_refraction + 4.4)))
            refraction_correction = refraction_correction_arcmin / 60.0 # convert arcminutes to degrees
        
        alt_deg_apparent = alt_deg + refraction_correction
        solar_zenith_deg = 90.0 - alt_deg_apparent

        return {
            "solar_azimuth_deg": round(az_deg_final, self.output_precision_config),
            "solar_elevation_deg": round(alt_deg_apparent, self.output_precision_config), # This is the apparent elevation
            "solar_zenith_deg": round(solar_zenith_deg, self.output_precision_config),
            "apparent_elevation_deg": round(alt_deg_apparent, self.output_precision_config),
            "geometric_elevation_deg_no_refraction": round(alt_deg, self.output_precision_config),
            "refraction_correction_deg": round(refraction_correction, self.output_precision_config + 2),
            "calculation_model_used": "spherical_approx_v2_bennett_refraction"
        }

    def _run(
        self,
        latitude: float,
        longitude: float,
        utc_timestamp_iso: str,
        elevation_m: Optional[float] = 0.0 # Pydantic ensures this has a value or default
    ) -> str:
        response: Dict[str, Any] = {"success": False}

        try:
            # Pydantic has already validated the input types and basic ISO format.
            # Convert ISO string to datetime object, ensuring it's UTC.
            if not utc_timestamp_iso.endswith('Z') and '+' not in utc_timestamp_iso[10:] and (len(utc_timestamp_iso) <= 10 or '-' not in utc_timestamp_iso[10:]):
                 # If no 'Z' and no offset part that looks like an offset, assume it's naive but meant to be UTC.
                 dt_obj_naive = datetime.fromisoformat(utc_timestamp_iso)
                 dt_utc = dt_obj_naive.replace(tzinfo=timezone.utc)
            else:
                dt_utc = datetime.fromisoformat(utc_timestamp_iso.replace('Z', '+00:00'))

            # Ensure it's UTC, then make naive for calculations
            dt_utc_naive_for_calc = dt_utc.astimezone(timezone.utc).replace(tzinfo=None)

        except ValueError as e:
            logger.error(f"Timestamp processing error for '{utc_timestamp_iso}': {e}")
            response["error"] = f"Invalid UTC timestamp format or value: '{utc_timestamp_iso}'. Details: {e}"
            return json.dumps(response)

        actual_elevation_m = elevation_m if elevation_m is not None else 0.0

        try:
            solar_data = self._calculate_solar_position_spherical(
                dt_utc_naive_for_calc, latitude, longitude, actual_elevation_m
            )
            response.update(solar_data)
            response["success"] = True

            # Determine lighting period
            apparent_elevation = solar_data["apparent_elevation_deg"]
            # Standard definitions for twilight (degrees of sun below horizon)
            # Civil twilight: 0 to -6 degrees
            # Nautical twilight: -6 to -12 degrees
            # Astronomical twilight: -12 to -18 degrees
            if apparent_elevation > 0.25: # Sun clearly above horizon (disk + some margin)
                lighting_period = "Daytime"
            elif apparent_elevation > -0.833: # Sun's upper limb on horizon to ~0.25 deg (includes part of golden hour)
                lighting_period = "Sunrise/Sunset (Golden Hour part 1)"
            elif apparent_elevation > -6: # Civil Twilight (Golden Hour part 2 / Blue Hour start)
                lighting_period = "Civil Twilight (Golden/Blue Hour transition)"
            elif apparent_elevation > -12: # Nautical Twilight (Blue Hour main / Deep Blue Hour)
                lighting_period = "Nautical Twilight (Blue Hour)"
            elif apparent_elevation > -18: # Astronomical Twilight
                lighting_period = "Astronomical Twilight"
            else: # Night
                lighting_period = "Nighttime"
            response["lighting_period"] = lighting_period
            response["utc_timestamp_processed"] = dt_utc.isoformat()


        except Exception as e:
            logger.exception(f"Error during solar position calculation for lat={latitude}, lon={longitude}, time='{utc_timestamp_iso}'")
            response["error"] = f"Error during solar position calculation: {str(e)}"

        return json.dumps(response, indent=2)

if __name__ == '__main__':
    # Example Usage
    tool = SolarPositionAnalyzerTool()
    
    # Test cases
    test_cases = [
        {"latitude": 34.0522, "longitude": -118.2437, "utc_timestamp_iso": "2023-10-27T00:30:00Z", "elevation_m": 70}, # LA, around sunset
        {"latitude": 51.5074, "longitude": 0.1278, "utc_timestamp_iso": "2023-10-26T12:00:00Z", "elevation_m": 11},    # London, midday
        {"latitude": -33.8688, "longitude": 151.2093, "utc_timestamp_iso": "2023-10-27T06:00:00+11:00"}, # Sydney, morning (with offset)
        {"latitude": 78.2232, "longitude": 15.6267, "utc_timestamp_iso": "2023-12-20T12:00:00Z"}, # Svalbard, polar night
        {"latitude": 0, "longitude": 0, "utc_timestamp_iso": "2023-03-20T12:00:00Z"}, # Equator, equinox noon
        {"latitude": 40.7128, "longitude": -74.0060, "utc_timestamp_iso": "2024-01-01T23:00:00-05:00"} # NYC New Year with offset
    ]

    for i, case in enumerate(test_cases):
        print(f"--- Test Case {i+1} ---")
        print(f"Input: {case}")
        result = tool._run(**case)
        print(f"Output: {result}\\n")

    # Example with Pydantic validation error
    print("--- Test Case: Invalid Latitude ---")
    try:
        invalid_case = {"latitude": 95.0, "longitude": 0, "utc_timestamp_iso": "2023-01-01T12:00:00Z"}
        # Manually trigger validation for demonstration if _run doesn't directly take the model
        # SolarPositionInput(**invalid_case) # This would raise error
        # For tools, CrewAI handles this. We can simulate the args for _run.
        print(f"Input: {invalid_case}")
        result = tool._run(**invalid_case) # Pydantic validation should prevent this if called by CrewAI
        print(f"Output: {result}\\n")
    except Exception as e:
        print(f"Error (expected for invalid input): {e}\\n")
        
    print("--- Test Case: Invalid Timestamp Format ---")
    try:
        invalid_case_ts = {"latitude": 0, "longitude": 0, "utc_timestamp_iso": "2023/01/01 12:00:00"}
        print(f"Input: {invalid_case_ts}")
        # To see Pydantic validation, you'd typically construct the model:
        # validated_input = SolarPositionInput(**invalid_case_ts)
        # result = tool._run(**validated_input.model_dump())
        # CrewAI will do this. For direct _run, Pydantic model isn't explicitly passed unless we change _run
        # If we call _run directly as is, its internal parsing will fail or Pydantic via args_schema
        # If args_schema is properly used by CrewAI, this would be caught before _run
        # Simulating how CrewAI might pass validated args, or letting _run's parsing catch it.
        result = tool._run(**invalid_case_ts)
        print(f"Output: {result}\\n")
    except Exception as e: # Catch broader exceptions if _run itself raises something before Pydantic takes full effect
        print(f"Error (expected for invalid input): {e}\\n")
