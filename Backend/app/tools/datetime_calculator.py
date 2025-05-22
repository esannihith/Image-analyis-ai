# app/tools/datetime_calculator.py
import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
from datetime import datetime, timezone, timedelta, time as dt_time # Added dt_time alias
import re # For parsing offset strings

# Attempt to import pytz, fallback to zoneinfo for Python 3.9+
try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        ZONEINFO_AVAILABLE = True
    except ImportError:
        ZONEINFO_AVAILABLE = False


# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        # Assuming these tools are listed under a "TemporalTools" key in tools.yaml
        # based on the file structure of other similar tools.
        tool_config = yaml.safe_load(f).get("TemporalTools", {}).get("DateTimeCalculator", {}).get("config", {})
except Exception:
    tool_config = {}


class DateTimeCalculatorInput(BaseModel):
    """Input schema for DateTimeCalculatorTool."""
    metadata: Dict[str, Any] = Field(..., description="Image metadata dictionary. Expected to contain EXIF date/time tags like 'DateTimeOriginal', 'OffsetTimeOriginal', 'SubSecTimeOriginal', etc.")
    # Optionally allow overriding default output timezone and format
    output_timezone: Optional[str] = Field(None, description="Desired output timezone (e.g., 'America/New_York', 'UTC'). Overrides tool config.")
    output_format: Optional[str] = Field(None, description="Desired output datetime format string (strftime format) or 'ISO8601'. Overrides tool config.")


class DateTimeCalculatorTool(BaseTool):
    name: str = "DateTime Processor"
    description: str = (
        "Extracts, calculates, and formats date and time information from image metadata. "
        "It determines the most accurate capture time, converts to a specified timezone (default UTC), "
        "formats it (default ISO8601), and identifies the period of the day."
    )
    args_schema: Type[BaseModel] = DateTimeCalculatorInput

    # Configuration from YAML/env
    default_output_timezone_config: str = tool_config.get("timezone", os.getenv("DATETIME_DEFAULT_TZ", "UTC"))
    default_output_format_config: str = tool_config.get("format", os.getenv("DATETIME_DEFAULT_FORMAT", "ISO8601"))

    def _parse_exif_datetime_with_offset(self, dt_str: Optional[str], offset_str: Optional[str] = None, subsec_str: Optional[str] = None) -> Optional[datetime]:
        """
        Parses an EXIF datetime string (typically 'YYYY:MM:DD HH:MM:SS') and an optional offset string.
        Handles potential subseconds.
        """
        if not dt_str:
            return None
        
        try:
            # Standard EXIF datetime format
            dt_obj = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
            
            # Add subseconds if available
            if subsec_str:
                try:
                    # SubSecTimeOriginal is usually just the subsecond part, e.g., "123" for 123ms
                    microseconds = int(subsec_str.ljust(6, '0')[:6]) # Pad/truncate to 6 digits for microseconds
                    dt_obj = dt_obj.replace(microsecond=microseconds)
                except ValueError:
                    pass # Ignore invalid subsec

            # Apply timezone offset if provided
            if offset_str:
                # Offset format can be like "+HH:MM", "-HH:MM", "Z", or just "+HHMM"
                offset_str = offset_str.strip()
                if offset_str == 'Z':
                    dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                else:
                    match = re.fullmatch(r'([+-])(\d{2}):?(\d{2})?', offset_str)
                    if match:
                        sign, hh, mm = match.groups()
                        mm = mm or '00' # if "HH" only was provided (unlikely for EXIF, but robust)
                        delta_hours = int(hh)
                        delta_minutes = int(mm)
                        total_offset_minutes = (delta_hours * 60 + delta_minutes) * (-1 if sign == '-' else 1)
                        tz = timezone(timedelta(minutes=total_offset_minutes))
                        dt_obj = dt_obj.replace(tzinfo=tz)
            return dt_obj
        except ValueError:
            return None # Invalid datetime string format

    def _get_best_datetime(self, metadata: Dict[str, Any]) -> Optional[datetime]:
        """
        Extracts the best possible datetime object from metadata, prioritizing original capture time with offset.
        """
        # Prioritize DateTimeOriginal with its specific offset and subseconds
        dt_orig_str = metadata.get("DateTimeOriginal") or metadata.get("EXIF:DateTimeOriginal")
        offset_orig_str = metadata.get("OffsetTimeOriginal") or metadata.get("EXIF:OffsetTimeOriginal")
        subsec_orig_str = metadata.get("SubSecTimeOriginal") or metadata.get("EXIF:SubSecTimeOriginal")
        
        dt_obj = self._parse_exif_datetime_with_offset(dt_orig_str, offset_orig_str, subsec_orig_str)
        if dt_obj:
            return dt_obj

        # Fallback: DateTimeDigitized with its offset
        dt_digi_str = metadata.get("DateTimeDigitized") or metadata.get("EXIF:DateTimeDigitized")
        offset_digi_str = metadata.get("OffsetTimeDigitized") or metadata.get("EXIF:OffsetTimeDigitized")
        subsec_digi_str = metadata.get("SubSecTimeDigitized") or metadata.get("EXIF:SubSecTimeDigitized")
        dt_obj = self._parse_exif_datetime_with_offset(dt_digi_str, offset_digi_str, subsec_digi_str)
        if dt_obj:
            return dt_obj

        # Fallback: General DateTime tag (often modification date, less reliable for capture)
        # This might not have an offset tag directly associated in the same way.
        dt_mod_str = metadata.get("DateTime") or metadata.get("EXIF:DateTime")
        # No standard 'OffsetTime' for general DateTime, might need to check 'OffsetTime' if available generally
        offset_gen_str = metadata.get("OffsetTime") or metadata.get("EXIF:OffsetTime") # General offset
        subsec_gen_str = metadata.get("SubSecTime") or metadata.get("EXIF:SubSecTime")

        dt_obj = self._parse_exif_datetime_with_offset(dt_mod_str, offset_gen_str, subsec_gen_str)
        if dt_obj:
            return dt_obj
        
        # Fallback: GPSDateStamp and GPSTimeStamp (always UTC)
        gps_date_str = metadata.get("GPSDateStamp") or metadata.get("EXIF:GPSDateStamp") # Format 'YYYY:MM:DD'
        gps_time_tuple = metadata.get("GPSTimeStamp") or metadata.get("EXIF:GPSTimeStamp") # Tuple of rationals (H, M, S)

        if gps_date_str and gps_time_tuple and isinstance(gps_time_tuple, (list, tuple)) and len(gps_time_tuple) == 3:
            try:
                # GPS time is often array of rationals or floats
                h = int(float(gps_time_tuple[0]))
                m = int(float(gps_time_tuple[1]))
                s_float = float(gps_time_tuple[2])
                s = int(s_float)
                ms = int((s_float - s) * 1_000_000) # microseconds

                gps_dt_str = f"{gps_date_str} {h:02d}:{m:02d}:{s:02d}"
                dt_obj = datetime.strptime(gps_dt_str, '%Y:%m:%d %H:%M:%S')
                dt_obj = dt_obj.replace(microsecond=ms, tzinfo=timezone.utc) # GPS time is UTC
                return dt_obj
            except (ValueError, TypeError):
                pass
        return None

    def _convert_to_target_timezone(self, dt_obj: datetime, target_tz_str: str) -> Optional[datetime]:
        if not dt_obj.tzinfo: # If datetime is naive, assume it's in UTC as a last resort or system local.
                              # For robustness, EXIF parsing should strive to make it offset-aware.
                              # Here, if it's naive from parsing, let's assume UTC based on default config logic.
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)

        if target_tz_str.upper() == "UTC":
            return dt_obj.astimezone(timezone.utc)

        if PYTZ_AVAILABLE:
            try:
                target_tz = pytz.timezone(target_tz_str)
                return dt_obj.astimezone(target_tz)
            except pytz.UnknownTimeZoneError:
                return None # Unknown timezone
        elif ZONEINFO_AVAILABLE: # Python 3.9+
            try:
                target_tz = ZoneInfo(target_tz_str)
                return dt_obj.astimezone(target_tz)
            except ZoneInfoNotFoundError:
                return None
        else: # No timezone library available, can only handle UTC or system local (which is risky)
            if target_tz_str.upper() == "UTC": # Already handled
                 return dt_obj.astimezone(timezone.utc)
            # Cannot convert to other named timezones without pytz or zoneinfo
            return None


    def _format_datetime(self, dt_obj: datetime, format_str: str) -> str:
        if format_str.upper() == "ISO8601":
            return dt_obj.isoformat()
        try:
            return dt_obj.strftime(format_str)
        except ValueError: # Invalid format string
            return dt_obj.isoformat() # Fallback to ISO8601

    def _get_day_period(self, dt_obj: datetime) -> str:
        """Determines the period of the day (morning, afternoon, evening, night) based on local time."""
        # Ensure dt_obj is timezone-aware. If converted to target_tz, it should be.
        # If still naive, this might be inaccurate or based on system's idea of local.
        # We operate on the hour of the (potentially timezone-converted) datetime object.
        hour = dt_obj.hour
        if dt_time(6, 0) <= dt_obj.time() < dt_time(12, 0):
            return "morning"
        elif dt_time(12, 0) <= dt_obj.time() < dt_time(17, 0):
            return "afternoon"
        elif dt_time(17, 0) <= dt_obj.time() < dt_time(21, 0):
            return "evening"
        else: # Covers 21:00 to 05:59
            return "night"

    def _run(self, metadata: Dict[str, Any], output_timezone: Optional[str] = None, output_format: Optional[str] = None) -> str:
        response: Dict[str, Any] = {"success": False}

        target_tz_str = output_timezone or self.default_output_timezone_config
        target_format_str = output_format or self.default_output_format_config
        
        source_dt = self._get_best_datetime(metadata)

        if not source_dt:
            response["error"] = "Could not determine a valid primary datetime from metadata."
            return json.dumps(response)
        
        response["source_datetime_extracted"] = source_dt.isoformat() # Log what was initially parsed

        # Convert to target timezone
        converted_dt = self._convert_to_target_timezone(source_dt, target_tz_str)
        if not converted_dt:
            response["error"] = f"Failed to convert datetime to target timezone '{target_tz_str}'. Timezone library (pytz or zoneinfo) might be missing or timezone is invalid."
            # Fallback to using source_dt for formatting if conversion failed but source_dt is aware
            if source_dt.tzinfo:
                 converted_dt = source_dt # Use source if it was already aware
            else: # If source was naive and conversion failed (e.g. no pytz/zoneinfo for non-UTC)
                 converted_dt = source_dt.replace(tzinfo=timezone.utc) # Assume UTC for naive source before formatting
                 response["warning"] = f"Could not convert to {target_tz_str}. Outputting as UTC (assumed for naive source)."
                 target_tz_str = "UTC" # Reflect this assumption

        formatted_dt_str = self._format_datetime(converted_dt, target_format_str)
        day_period = self._get_day_period(converted_dt) # Get day period from the (potentially) converted datetime

        response.update({
            "success": True,
            "timestamp": formatted_dt_str,
            "timezone": target_tz_str, # The actual timezone of the outputted timestamp
            "day_period": day_period,
            "original_timestamp_utc_if_known": source_dt.astimezone(timezone.utc).isoformat() if source_dt.tzinfo else "Source naive, UTC unknown"
        })
        
        return json.dumps(response, default=str)
