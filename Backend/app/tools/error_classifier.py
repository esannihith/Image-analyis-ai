import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from crewai.tools import BaseTool
import json
import traceback # To capture and pass traceback strings

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("ErrorTools", {}).get("ErrorClassifier", {}).get("config", {})
except Exception:
    tool_config = {}

class ErrorInputDetail(BaseModel):
    """Structured detail for an error."""
    error_type: Optional[str] = Field(None, description="The type/class of the error (e.g., 'ValueError', 'requests.exceptions.Timeout').")
    error_message: str = Field(..., description="The main error message string.")
    traceback_str: Optional[str] = Field(None, description="A string representation of the error's traceback (if available).")
    source_agent: Optional[str] = Field(None, description="The agent that reported or encountered the error.")
    source_tool: Optional[str] = Field(None, description="The tool that reported or encountered the error.")
    additional_context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Any other relevant context about the error.")


class ErrorClassifierInput(BaseModel):
    """Input schema for ErrorClassifierTool."""
    error_details: Union[str, ErrorInputDetail] = Field(..., description="The error to classify. Can be a simple string or a structured ErrorInputDetail object.")
    # session_id: Optional[str] = Field(None, description="Optional session ID for logging/context.")

class ErrorClassificationOutput(BaseModel):
    """Structured output for error classification."""
    original_error_message: str
    original_error_type: Optional[str] = None
    error_category: str
    assigned_severity: str
    suggested_notification_channels: List[str]
    analysis_details: str
    source_context: Dict[str, Optional[str]] = {}


class ErrorClassifierTool(BaseTool):
    name: str = "System Error Classifier"
    description: str = (
        "Analyzes and categorizes system or operational errors, assigning a severity level "
        "and suggesting notification channels based on predefined rules and configurations."
    )
    args_schema: Type[BaseModel] = ErrorClassifierInput

    # Configuration from YAML/env
    severity_levels_config: List[str] = tool_config.get("severity_levels", ["critical", "error", "warning", "info"])
    notification_channels_config: List[str] = tool_config.get("notification_channels", ["logs", "email"])

    # Simple rule-based classification
    # Keywords for categories and severities. Can be expanded.
    # Order matters for some keyword checks (more specific first).
    CLASSIFICATION_RULES = [
        # Category: API/Network Errors
        ({"keywords": ["timeout", "connection refused", "dns lookup failed", "network is unreachable", "sslerror", "host not found", "api key invalid", "authentication failed", "rate limit exceeded", "service unavailable", "500 internal server error", "502 bad gateway", "503 service unavailable", "504 gateway timeout"], "category": "ExternalServiceError", "severity": "critical"}, ["logs", "email"]),
        ({"keywords": ["requests.exceptions", "urllib3.exceptions"], "category": "NetworkLibraryError", "severity": "error"}, ["logs"]),
        # Category: Data/Input Errors
        ({"keywords": ["invalid input", "validationerror", "missing required field", "typeerror for argument", "valueerror", "jsondecodeerror", "parsing error", "data format error", "unsupported format", "schema validation failed"], "category": "DataValidationError", "severity": "error"}, ["logs"]),
        ({"keywords": ["filenotfound", "no such file or directory"], "category": "FileSystemError", "severity": "error"}, ["logs"]),
        # Category: Configuration Errors
        ({"keywords": ["config file not found", "missing configuration", "invalid config value"], "category": "ConfigurationError", "severity": "critical"}, ["logs", "email"]),
        # Category: Tool/Internal Errors
        ({"keywords": ["tool execution failed", "internal logic error", "unexpected tool behavior"], "category": "ToolExecutionError", "severity": "error"}, ["logs"]),
        # Category: Resource Errors
        ({"keywords": ["out of memory", "disk space full", "resource temporarily unavailable"], "category": "ResourceLimitError", "severity": "critical"}, ["logs", "email"]),
        # Default / Fallback
        ({"keywords": [], "category": "UnknownError", "severity": "warning"}, ["logs"]) # Default if no other rules match
    ]


    def _classify_error(self, error_message: str, error_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Classifies the error based on keywords in the message and type.
        Returns a dict with "category", "severity", and "suggested_notifications".
        """
        error_message_lower = error_message.lower()
        error_type_lower = error_type.lower() if error_type else ""

        for rule_entry in self.CLASSIFICATION_RULES:
            rule = rule_entry[0]
            notifications = rule_entry[1]
            
            # Check if any keyword matches
            matched_keyword = False
            if not rule["keywords"]: # Default rule if keywords list is empty
                matched_keyword = True
            else:
                for keyword in rule["keywords"]:
                    if keyword in error_message_lower or keyword in error_type_lower:
                        matched_keyword = True
                        break
            
            if matched_keyword:
                # Validate severity against configured levels, fallback to a default if not in config
                severity = rule["severity"]
                if severity not in self.severity_levels_config:
                    severity = self.severity_levels_config[-1] if self.severity_levels_config else "warning" # Fallback to last configured or 'warning'
                
                # Filter suggested notifications based on configured channels
                suggested_notifications = [ch for ch in notifications if ch in self.notification_channels_config]
                if not suggested_notifications and self.notification_channels_config: # If filtering results in empty, use first configured channel
                    suggested_notifications = [self.notification_channels_config[0]]
                elif not self.notification_channels_config: # No channels configured at all
                    suggested_notifications = []


                return {
                    "category": rule["category"],
                    "severity": severity,
                    "suggested_notifications": suggested_notifications,
                    "matched_rule_keywords": rule["keywords"] # For debugging/transparency
                }
        
        # Should not be reached if default rule exists, but as a safeguard:
        return {
            "category": "UnclassifiedError", 
            "severity": self.severity_levels_config[-1] if self.severity_levels_config else "info",
            "suggested_notifications": [self.notification_channels_config[0]] if self.notification_channels_config else []
        }

    def _run(self, error_details: Union[str, Dict[str, Any]]) -> str:
        response: Dict[str, Any] = {"success": False}

        original_error_msg_str: str
        original_error_type_str: Optional[str] = None
        source_context: Dict[str, Optional[str]] = {}
        analysis_details_str = "Error processed by classifier."

        try:
            if isinstance(error_details, str):
                original_error_msg_str = error_details
                analysis_details_str = "Simple error string provided. Classification based on message content."
                # Could try to infer type if it's like "ValueError: Some message"
                if ":" in original_error_msg_str:
                    parts = original_error_msg_str.split(":", 1)
                    potential_type = parts[0].strip()
                    # Basic check if it looks like a Python exception type
                    if 'Error' in potential_type or 'Exception' in potential_type and not ' ' in potential_type:
                        original_error_type_str = potential_type
                        original_error_msg_str = parts[1].strip() if len(parts) > 1 else ""


            elif isinstance(error_details, dict): # Assuming it's a dict that can be parsed by ErrorInputDetail
                try:
                    parsed_details = ErrorInputDetail(**error_details)
                    original_error_msg_str = parsed_details.error_message
                    original_error_type_str = parsed_details.error_type
                    source_context["source_agent"] = parsed_details.source_agent
                    source_context["source_tool"] = parsed_details.source_tool
                    if parsed_details.traceback_str:
                        analysis_details_str = f"Structured error provided. Traceback available. Context: {parsed_details.additional_context or 'N/A'}"
                    else:
                        analysis_details_str = f"Structured error provided. Context: {parsed_details.additional_context or 'N/A'}"
                except Exception as p_error: # Pydantic ValidationError or other
                    original_error_msg_str = f"Could not parse structured error_details: {str(p_error)}. Raw input: {str(error_details)[:200]}"
                    analysis_details_str = "Failed to parse structured error input."
            else:
                original_error_msg_str = f"Unsupported error_details type: {type(error_details)}. Value: {str(error_details)[:200]}"
                analysis_details_str = "Unsupported input type."

            classification = self._classify_error(original_error_msg_str, original_error_type_str)

            output_data = ErrorClassificationOutput(
                original_error_message=original_error_msg_str,
                original_error_type=original_error_type_str,
                error_category=classification["category"],
                assigned_severity=classification["severity"],
                suggested_notification_channels=classification["suggested_notifications"],
                analysis_details=analysis_details_str,
                source_context=source_context
            )
            response.update(output_data.model_dump())
            response["success"] = True

        except Exception as e:
            # This is an error within the classifier tool itself
            response["success"] = False
            # Use traceback.format_exc() to get the traceback string for the current exception
            tb_str = traceback.format_exc()
            response["error"] = f"ErrorClassifierTool internal error: {str(e)}. Traceback: {tb_str}"
            response["original_input_processed"] = original_error_msg_str if 'original_error_msg_str' in locals() else "Input processing failed early."
            
        return json.dumps(response, default=str)
