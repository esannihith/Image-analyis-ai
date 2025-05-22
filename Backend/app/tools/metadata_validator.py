// ... existing code ...
import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, validator, root_validator
from crewai.tools import BaseTool
import json
from datetime import datetime # For validating datetime strings

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("MetadataTools", {}).get("MetadataValidator", {}).get("config", {})
except Exception:
    tool_config = {}

class MetadataValidatorInput(BaseModel):
    """Input schema for MetadataValidatorTool."""
    # Expects the `processed_data` dictionary from EXIFDecoderTool's output
    processed_metadata: Dict[str, Any] = Field(..., description="The processed metadata dictionary to validate (e.g., from EXIFDecoderTool's processed_data).")

class ValidationIssue(BaseModel):
    field: str
    issue: str
    severity: str # "error" or "warning"
    value_found: Optional[Any] = None # Add the value that caused the issue for better logging

# Helper function to get nested dictionary values using dot notation
def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    keys = path.split('.')
    current_level = data
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else:
            return default
    return current_level

# Helper function to check if a nested key exists
def nested_key_exists(data: Dict[str, Any], path: str) -> bool:
    keys = path.split('.')
    current_level = data
    for i, key in enumerate(keys):
        if isinstance(current_level, dict) and key in current_level:
            if i == len(keys) - 1: # Last key in path
                return True
            current_level = current_level[key]
        else:
            return False
    return False


class MetadataValidatorTool(BaseTool):
    name: str = "Image Metadata Validator"
    description: str = (
        "Validates processed image metadata (derived from EXIF, IPTC, XMP) against a defined set of rules or a schema. "
        "Checks for presence of mandatory fields, correct data types, and valid value ranges within the processed_data structure."
    )
    args_schema: Type[BaseModel] = MetadataValidatorInput

    # Configuration from YAML/env
    strict_mode_config: bool = tool_config.get("strict_mode", os.getenv("METADATA_VALIDATOR_STRICT", "True").lower() == 'true')
    allow_partial_config: bool = tool_config.get("allow_partial", os.getenv("METADATA_VALIDATOR_PARTIAL", "False").lower() == 'true')

    # Updated schema keys to use dot notation for processed_data structure
    DEFAULT_SCHEMA_RULES: Dict[str, Dict[str, Any]] = {
        "camera_info.model": {"required": True, "type": str, "allow_empty_string": False},
        "camera_info.make": {"required": True, "type": str, "allow_empty_string": False},
        "datetime_info.date_time_original": {"required": True, "type": "datetime_str_exif", "allow_empty_string": False},
        "technical_settings.iso": {"required": True, "type": int, "range": [25, 1024000]},
        "technical_settings.exposure_time": {"required": True, "type": float, "range": [0.000001, 3600.0]}, # Assuming ExposureTime is processed to float
        "technical_settings.f_number": {"required": True, "type": float, "range": [0.5, 128.0]}, # Assuming FNumber is processed to float
        "technical_settings.focal_length": {"required": False, "type": float, "range": [1.0, 10000.0]},
        "camera_info.lens_model": {"required": False, "type": str, "allow_empty_string": True},
        "gps_info.latitude": {"required": False, "type": float, "range": [-90.0, 90.0]}, # Conditional on GPS info presence
        "gps_info.longitude": {"required": False, "type": float, "range": [-180.0, 180.0]},
        "copyright_info.copyright": {"required": False, "type": str, "allow_empty_string": True},
        # Example for a field from descriptive_info
        "descriptive_info.keywords": {"required": False, "type": list, "element_type": str, "allow_empty_list": True} 
    }

    def _validate_field(self, field_path: str, value: Any, rules: Dict[str, Any]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        field_type_rule = rules.get("type")
        
        type_ok = False
        current_value_for_further_checks = value

        if field_type_rule == str:
            if isinstance(value, str):
                type_ok = True
                if not rules.get("allow_empty_string", True) and not value.strip():
                    issues.append(ValidationIssue(field=field_path, issue="String value cannot be empty or just whitespace.", severity="error", value_found=value))
            else:
                 issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected string, got {type(value).__name__}.", severity="error", value_found=value))
        elif field_type_rule == int:
            if isinstance(value, int):
                type_ok = True
            elif isinstance(value, str) and value.isdigit():
                 try:
                    current_value_for_further_checks = int(value)
                    type_ok = True
                 except ValueError:
                    issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected integer, got string that's not a valid int: '{str(value)[:50]}'.", severity="error", value_found=value))
            elif isinstance(value, float) and value.is_integer(): # Allow float if it's a whole number e.g. 100.0
                current_value_for_further_checks = int(value)
                type_ok = True
            else:
                issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected integer, got {type(value).__name__}: '{str(value)[:50]}'.", severity="error", value_found=value))
        elif field_type_rule == float:
            if isinstance(value, (float, int)):
                current_value_for_further_checks = float(value)
                type_ok = True
            elif isinstance(value, str):
                try:
                    current_value_for_further_checks = float(value)
                    type_ok = True
                except ValueError:
                    issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected float, got string that's not a valid float: '{str(value)[:50]}'.", severity="error", value_found=value))
            else:
                issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected float, got {type(value).__name__}: '{str(value)[:50]}'.", severity="error", value_found=value))
        elif field_type_rule == "datetime_str_exif": # Specific format YYYY:MM:DD HH:MM:SS
            if isinstance(value, str):
                try:
                    datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    type_ok = True
                    if not rules.get("allow_empty_string", True) and not value.strip():
                         issues.append(ValidationIssue(field=field_path, issue="Datetime string value cannot be empty.", severity="error", value_found=value))
                except ValueError:
                    issues.append(ValidationIssue(field=field_path, issue=f"Invalid datetime format. Expected 'YYYY:MM:DD HH:MM:SS', got '{value}'.", severity="error", value_found=value))
            else:
                issues.append(ValidationIssue(field=field_path, issue=f"Invalid type for datetime string. Expected string, got {type(value).__name__}.", severity="error", value_found=value))
        elif field_type_rule == list: # Basic list validation
            if isinstance(value, list):
                type_ok = True
                if not rules.get("allow_empty_list", True) and not value:
                    issues.append(ValidationIssue(field=field_path, issue="List cannot be empty.", severity="error", value_found=value))
                # Optionally, validate element types
                element_type_rule = rules.get("element_type")
                if element_type_rule:
                    for i, item in enumerate(value):
                        item_type_ok = False
                        if element_type_rule == str and isinstance(item, str): item_type_ok = True
                        elif element_type_rule == int and isinstance(item, int): item_type_ok = True
                        # Add more element types as needed
                        if not item_type_ok:
                            issues.append(ValidationIssue(field=f"{field_path}[{i}]", issue=f"Invalid list element type. Expected {element_type_rule.__name__ if hasattr(element_type_rule, '__name__') else element_type_rule}, got {type(item).__name__}.", severity="error", value_found=item))
            else:
                issues.append(ValidationIssue(field=field_path, issue=f"Invalid type. Expected list, got {type(value).__name__}.", severity="error", value_found=value))

        else: 
            type_ok = True # Unknown type in schema, assume pass for type check or add more types

        if not type_ok:
            return issues

        if "range" in rules and isinstance(current_value_for_further_checks, (int, float)):
            min_val, max_val = rules["range"]
            if not (min_val <= current_value_for_further_checks <= max_val):
                issues.append(ValidationIssue(field=field_path, issue=f"Value {current_value_for_further_checks} out of allowed range [{min_val}, {max_val}].", severity="error", value_found=current_value_for_further_checks))

        if "allowed_values" in rules and current_value_for_further_checks not in rules["allowed_values"]:
            issues.append(ValidationIssue(field=field_path, issue=f"Value '{current_value_for_further_checks}' not in allowed values: {rules['allowed_values']}.", severity="error", value_found=current_value_for_further_checks))
            
        return issues

    def _run(self, processed_metadata: Dict[str, Any]) -> str:
        results: Dict[str, Any] = {
            "tool_execution_success": True, # Tool execution success
            "validation_status": "unknown",
            "errors": [],
            "warnings": [],
            "validated_fields_summary": {"checked": 0, "passed": 0, "failed_strict": 0, "missing_required": 0},
            "config_used": {"strict_mode": self.strict_mode_config, "allow_partial": self.allow_partial_config}
        }
        
        if not processed_metadata:
            results["validation_status"] = "no_metadata_provided"
            results["errors"].append(ValidationIssue(field="processed_metadata", issue="No metadata provided to validate.", severity="error").model_dump())
            return json.dumps(results, default=str)

        all_issues: List[ValidationIssue] = []
        
        for field_path, rules in self.DEFAULT_SCHEMA_RULES.items():
            results["validated_fields_summary"]["checked"] += 1
            is_required = rules.get("required", False)
            
            # Use helper to check existence and get value for nested keys
            field_exists = nested_key_exists(processed_metadata, field_path)
            value = get_nested_value(processed_metadata, field_path) if field_exists else None

            if field_exists:
                field_issues = self._validate_field(field_path, value, rules)
                if field_issues:
                    all_issues.extend(field_issues)
                    # Count as failed_strict if any error-level issue for this field
                    if any(iss.severity == "error" for iss in field_issues):
                        results["validated_fields_summary"]["failed_strict"] += 1
                else:
                    results["validated_fields_summary"]["passed"] += 1
            elif is_required:
                severity = "error" # Missing required is always an error, strict_mode affects overall status
                all_issues.append(ValidationIssue(field=field_path, issue="Mandatory field is missing.", severity=severity))
                results["validated_fields_summary"]["missing_required"] += 1
                results["validated_fields_summary"]["failed_strict"] += 1 # Missing required is a strict failure

            # This logic might need adjustment based on how "allow_partial" should treat missing optional fields.
            # If allow_partial is false, should missing optional fields be warnings or affect status?
            # For now, only missing *required* fields affect "failed_strict" or "missing_required".
            # Missing optional fields don't add warnings here unless explicitly defined by a rule.


        for issue in all_issues:
            if issue.severity == "error":
                results["errors"].append(issue.model_dump(exclude_none=True))
            else:
                results["warnings"].append(issue.model_dump(exclude_none=True))

        # Determine overall validation_status
        # This logic is complex and might need further refinement based on precise definitions
        # of "invalid", "partially_valid", etc., especially concerning strict_mode and allow_partial.

        has_errors = bool(results["errors"])
        has_warnings = bool(results["warnings"])

        if self.strict_mode_config:
            if results["validated_fields_summary"]["failed_strict"] > 0 or results["validated_fields_summary"]["missing_required"] > 0:
                results["validation_status"] = "invalid_strict"
            elif has_warnings and not self.allow_partial_config: # Strict, warnings exist, partial not allowed
                 results["validation_status"] = "valid_with_warnings_strict_disallow_partial"
            elif has_warnings: # Strict, warnings exist, partial allowed
                 results["validation_status"] = "valid_with_warnings_strict_allow_partial"
            else: # Strict, no errors, no warnings
                results["validation_status"] = "valid_strict"
        else: # Not strict_mode
            if has_errors: # Non-strict, but errors exist
                results["validation_status"] = "invalid_non_strict"
            elif has_warnings and not self.allow_partial_config:
                results["validation_status"] = "valid_with_warnings_non_strict_disallow_partial"
            elif has_warnings: # Non-strict, warnings exist, partial allowed
                results["validation_status"] = "valid_with_warnings_non_strict_allow_partial"
            else: # Non-strict, no errors, no warnings
                results["validation_status"] = "valid_non_strict"
        
        # A simpler overarching status if any error occurred
        if has_errors:
            results["overall_valid"] = False
        else:
            results["overall_valid"] = True


        return json.dumps(results, default=str)
