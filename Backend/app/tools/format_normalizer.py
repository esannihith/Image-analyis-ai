import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
from datetime import datetime, timezone, timedelta
import re
import copy # For deepcopy

# Attempt to import pytz, fallback to zoneinfo for Python 3.9+
try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False
    pytz = None # Placeholder
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        ZONEINFO_AVAILABLE = True
    except ImportError:
        ZONEINFO_AVAILABLE = False
        ZoneInfo = None # Placeholder
        ZoneInfoNotFoundError = None # Placeholder


# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("MetadataTools", {}).get("FormatNormalizer", {}).get("config", {})
except Exception:
    tool_config = {}

class FormatNormalizerInput(BaseModel):
    """Input schema for FormatNormalizerTool."""
    # Expects the `processed_data` dictionary from EXIFDecoderTool's output
    processed_metadata: Dict[str, Any] = Field(..., description="The processed metadata dictionary to normalize (e.g., from EXIFDecoderTool's processed_data).")
    target_timezone_override: Optional[str] = Field(None, description="Target timezone for date/time fields (e.g., 'UTC', 'America/New_York'). Overrides tool config.")

# Helper functions for nested dictionary access
def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    keys = path.split('.')
    current_level = data
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else:
            return default
    return current_level

def set_nested_value(data: Dict[str, Any], path: str, value: Any):
    keys = path.split('.')
    current_level = data
    for i, key in enumerate(keys[:-1]):
        current_level = current_level.setdefault(key, {})
        if not isinstance(current_level, dict): # Should not happen if used correctly
            return 
    current_level[keys[-1]] = value

def nested_key_exists(data: Dict[str, Any], path: str) -> bool:
    keys = path.split('.')
    current_level = data
    for i, key in enumerate(keys):
        if isinstance(current_level, dict) and key in current_level:
            if i == len(keys) - 1:
                return True
            current_level = current_level[key]
        else:
            return False
    return False


class FormatNormalizerTool(BaseTool):
    name: str = "Metadata Format Normalizer"
    description: str = (
        "Normalizes various metadata fields within the 'processed_data' structure to a consistent format. "
        "Focuses on date/time conversion to a target timezone and EXIF-style string format, "
        "numeric type consistency, and basic string cleaning."
    )
    args_schema: Type[BaseModel] = FormatNormalizerInput

    target_timezone_config: str = tool_config.get("timezone", os.getenv("METADATA_NORMALIZER_TZ", "UTC"))

    # Updated field paths to use dot notation for the processed_data structure.
    # These MUST align with the keys produced by EXIFDecoderTool's _process_key_metadata method.
    DATETIME_FIELDS_TO_NORMALIZE: List[str] = [
        "datetime_info.date_time_original",
        "datetime_info.date_time_digitized",
        "datetime_info.date_time",
        "gps_info.datestamp", # Combines with gps_info.timestamp
    ]
    OFFSET_FIELDS_TO_NORMALIZE: List[str] = [
        "datetime_info.offset_time_original",
        "datetime_info.offset_time_digitized",
        # "datetime_info.offset_time" # If EXIFDecoder produces this for DateTime
    ]
    NUMERIC_FIELDS: Dict[str, Type] = {
        "technical_settings.iso": int,
        "technical_settings.exposure_time": float, # Assuming EXIFDecoderTool produces this key
        "technical_settings.f_number": float,     # Assuming EXIFDecoderTool produces this key
        "technical_settings.focal_length": float,
        "technical_settings.focal_length_35mm": float,
        # GPS values are often rationals or lists of rationals from pyexiv2,
        # EXIFDecoderTool's _process_key_metadata should convert them to simple floats first.
        "gps_info.latitude": float,
        "gps_info.longitude": float,
        "gps_info.altitude": float,
        "file_info.file_size_bytes": int, # Example from EXIFDecoder output structure
        # Add more known numeric fields from processed_data as needed
    }
    # For string cleaning, we'll iterate through all string values.

    def _parse_flexible_datetime(self, dt_val: Any, original_offset_val: Optional[str] = None) -> Optional[datetime]:
        if isinstance(dt_val, datetime):
            dt_obj = dt_val
        elif isinstance(dt_val, str):
            dt_val_stripped = dt_val.strip()
            if not dt_val_stripped: return None # Empty string
            try:
                if dt_val_stripped.endswith('Z'):
                     dt_obj = datetime.fromisoformat(dt_val_stripped[:-1] + '+00:00')
                # Check for timezone offset like +05:30 or -0800
                elif re.search(r'[+\-]\d{2}:?\d{2}$', dt_val_stripped):
                     dt_obj = datetime.fromisoformat(dt_val_stripped)
                else: # Potentially naive ISO or EXIF style
                    try:
                        dt_obj = datetime.fromisoformat(dt_val_stripped)
                    except ValueError: 
                        dt_obj = datetime.strptime(dt_val_stripped, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                return None
        else:
            return None

        if dt_obj and dt_obj.tzinfo is None and original_offset_val:
            offset_tz = self._parse_offset_string(original_offset_val)
            if offset_tz:
                dt_obj = dt_obj.replace(tzinfo=offset_tz)
        return dt_obj
        
    def _parse_offset_string(self, offset_str: Any) -> Optional[timezone]:
        if not isinstance(offset_str, str): return None
        offset_str = offset_str.strip()
        if not offset_str: return None
        if offset_str == 'Z':
            return timezone.utc
        match = re.fullmatch(r'([+-])(\d{2}):?(\d{2})?', offset_str)
        if match:
            sign, hh, mm = match.groups()
            mm = mm or '00'
            try:
                total_offset_minutes = (int(hh) * 60 + int(mm)) * (-1 if sign == '-' else 1)
                return timezone(timedelta(minutes=total_offset_minutes))
            except ValueError: return None
        return None

    def _convert_to_target_timezone(self, dt_obj: datetime, target_tz_str: str) -> Optional[datetime]:
        if not dt_obj.tzinfo: # If naive, make it aware, assuming UTC if no other info
             dt_obj = dt_obj.replace(tzinfo=timezone.utc) # Default assumption for naive times

        if target_tz_str.upper() == "UTC":
            return dt_obj.astimezone(timezone.utc)
        
        if PYTZ_AVAILABLE and pytz is not None:
            try:
                target_tz = pytz.timezone(target_tz_str)
                return dt_obj.astimezone(target_tz)
            except pytz.UnknownTimeZoneError: return None # Log this error
        elif ZONEINFO_AVAILABLE and ZoneInfo is not None and ZoneInfoNotFoundError is not None:
            try:
                target_tz = ZoneInfo(target_tz_str)
                return dt_obj.astimezone(target_tz)
            except ZoneInfoNotFoundError: return None # Log this error
        return dt_obj.astimezone(timezone.utc) # Fallback to UTC if specific tz lib fails

    def _normalize_gps_datetime(self, data_dict: Dict[str, Any], target_tz_str: str, issues: List[Dict[str, str]]):
        gps_date_str = get_nested_value(data_dict, "gps_info.datestamp")
        gps_time_val = get_nested_value(data_dict, "gps_info.timestamp") # pyexiv2 often returns list of Rationals

        if isinstance(gps_date_str, str) and isinstance(gps_time_val, (list, tuple)) and len(gps_time_val) == 3:
            try:
                # Ensure GPS time components are valid numbers
                h = int(float(str(gps_time_val[0]).split('/')[0])) # Handle potential Rational string
                m = int(float(str(gps_time_val[1]).split('/')[0]))
                s_float_str = str(gps_time_val[2]).split('/')[0]
                s_float = float(s_float_str)

                s, ms = int(s_float), int((s_float - int(s_float)) * 1_000_000)
                
                gps_dt_obj_naive = datetime.strptime(f"{gps_date_str.strip()} {h:02d}:{m:02d}:{s:02d}", '%Y:%m:%d %H:%M:%S')
                gps_dt_obj_utc = gps_dt_obj_naive.replace(microsecond=ms, tzinfo=timezone.utc) # GPS is always UTC

                converted_gps_dt = self._convert_to_target_timezone(gps_dt_obj_utc, target_tz_str)
                if converted_gps_dt:
                    set_nested_value(data_dict, "gps_info.normalized_gps_timestamp", converted_gps_dt.strftime('%Y:%m:%d %H:%M:%S'))
                    offset_str = converted_gps_dt.strftime('%z')
                    if offset_str:
                         set_nested_value(data_dict, "gps_info.normalized_gps_offset", f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str)==5 else offset_str)
                    elif target_tz_str.upper() == "UTC":
                         set_nested_value(data_dict, "gps_info.normalized_gps_offset", "Z")
                else:
                    issues.append({"field": "gps_info.timestamp/datestamp", "issue": f"Failed to convert GPS datetime to target timezone {target_tz_str}."})
            except Exception as e:
                issues.append({"field": "gps_info.timestamp/datestamp", "issue": f"Error processing GPS date/time: {str(e)}"})

    def _clean_strings_recursive(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._clean_strings_recursive(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_strings_recursive(item) for item in data]
        elif isinstance(data, str):
            return data.strip()
        return data

    def _run(self, processed_metadata: Dict[str, Any], target_timezone_override: Optional[str] = None) -> str:
        # Use deepcopy to avoid modifying the input dictionary if it's used elsewhere
        normalized_metadata = copy.deepcopy(processed_metadata)
        issues: List[Dict[str, str]] = []
        
        target_tz = target_timezone_override if target_timezone_override else self.target_timezone_config

        # 1. Normalize GPS Date/Time Fields first
        self._normalize_gps_datetime(normalized_metadata, target_tz, issues)

        # 2. Normalize general Date/Time Fields
        for field_path in self.DATETIME_FIELDS_TO_NORMALIZE:
            # Skip gps_info.datestamp as it's handled by _normalize_gps_datetime
            if field_path == "gps_info.datestamp": 
                continue

            original_value = get_nested_value(normalized_metadata, field_path)
            if original_value is not None: # Process only if field exists
                original_offset_path = ""
                if field_path == "datetime_info.date_time_original": original_offset_path = "datetime_info.offset_time_original"
                elif field_path == "datetime_info.date_time_digitized": original_offset_path = "datetime_info.offset_time_digitized"
                # Add more mappings if EXIFDecoderTool creates other specific offset fields for datetime_info.date_time
                
                original_offset_val = get_nested_value(normalized_metadata, original_offset_path) if original_offset_path else None
                
                dt_obj = self._parse_flexible_datetime(original_value, original_offset_val)
                if dt_obj:
                    converted_dt = self._convert_to_target_timezone(dt_obj, target_tz)
                    if converted_dt:
                        set_nested_value(normalized_metadata, field_path, converted_dt.strftime('%Y:%m:%d %H:%M:%S'))
                        
                        # Determine corresponding offset field path and set it
                        # Example: "datetime_info.date_time_original" -> "datetime_info.offset_time_original_normalized"
                        # For simplicity, let's assume EXIFDecoder already provides keys for offsets in datetime_info
                        # and we will update those or add new ones like "normalized_offset" within the same group.
                        base_offset_field_path = field_path.replace("date_time", "offset_time") # Heuristic
                        if "datetime_info.date_time" == field_path : base_offset_field_path = "datetime_info.offset_time"


                        offset_str = converted_dt.strftime('%z')
                        if offset_str:
                             formatted_offset = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else offset_str
                             set_nested_value(normalized_metadata, base_offset_field_path, formatted_offset)
                        elif target_tz.upper() == "UTC":
                             set_nested_value(normalized_metadata, base_offset_field_path, "Z")
                    else:
                        issues.append({"field": field_path, "issue": f"Failed to convert to target timezone {target_tz}."})
                elif isinstance(original_value, str) and original_value.strip(): # If it was a non-empty string but not parsable
                    issues.append({"field": field_path, "issue": f"Could not parse datetime string: '{str(original_value)[:50]}'."})
        
        # 3. Normalize standalone Offset Fields (if they exist and weren't handled as part of a datetime field)
        for field_path in self.OFFSET_FIELDS_TO_NORMALIZE:
            # Check if this offset was already set/normalized by the datetime logic above
            # This check can be complex. For now, we re-normalize if it exists as a string.
            offset_val = get_nested_value(normalized_metadata, field_path)
            if isinstance(offset_val, str):
                parsed_offset_tz = self._parse_offset_string(offset_val)
                if parsed_offset_tz:
                    if parsed_offset_tz == timezone.utc:
                        set_nested_value(normalized_metadata, field_path, "Z")
                    else:
                        total_minutes = int(parsed_offset_tz.utcoffset(None).total_seconds() / 60)
                        sign = '+' if total_minutes >= 0 else '-'
                        hh, mm = divmod(abs(total_minutes), 60)
                        set_nested_value(normalized_metadata, field_path, f"{sign}{hh:02d}:{mm:02d}")
                elif offset_val.strip(): # If non-empty but not parsable
                    issues.append({"field": field_path, "issue": f"Could not parse offset string: '{offset_val[:20]}'."})

        # 4. Normalize Numeric Fields
        for field_path, expected_type in self.NUMERIC_FIELDS.items():
            val = get_nested_value(normalized_metadata, field_path)
            if val is not None: # Process only if field exists and has a value
                try:
                    converted_val = None
                    if expected_type == int:
                        converted_val = int(float(str(val))) # str(val) handles various inputs, float handles "1.0"
                    elif expected_type == float:
                        converted_val = float(str(val))
                    
                    if converted_val is not None:
                         set_nested_value(normalized_metadata, field_path, converted_val)
                except (ValueError, TypeError):
                    issues.append({"field": field_path, "issue": f"Could not convert '{str(val)[:50]}' to {expected_type.__name__}."})

        # 5. Basic String Cleaning (recursively)
        normalized_metadata = self._clean_strings_recursive(normalized_metadata)

        response_payload = {
            "tool_execution_success": True, # Tool itself ran
            "normalized_metadata": normalized_metadata,
            "target_timezone_applied": target_tz,
            "issues": issues
        }
        return json.dumps(response_payload, default=str)
