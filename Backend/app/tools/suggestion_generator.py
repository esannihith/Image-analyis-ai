import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import random
import logging

# Configure a logger for this tool
logger = logging.getLogger(__name__)
# Configure logging in your main application setup if you want to see these logs.
# Example: logging.basicConfig(level=logging.DEBUG)

# Load configuration from tools.yaml
tool_config: Dict[str, Any] = {}
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    if config_path.exists():
        with open(config_path, encoding='utf-8') as f: # Added encoding
            tool_config_data = yaml.safe_load(f)
            if tool_config_data and isinstance(tool_config_data, dict):
                tool_config = tool_config_data.get("ErrorTools", {}).get("SuggestionGenerator", {}).get("config", {})
            else:
                logger.warning("tools.yaml for SuggestionGenerator is empty or not a dict. Using defaults.")
    else:
        logger.warning(f"tools.yaml not found at {config_path}. Using default config for SuggestionGenerator.")
except Exception as e:
    logger.error(f"Error loading tools.yaml for SuggestionGenerator: {e}. Using defaults.")

class SuggestionContextInput(BaseModel):
    """Context provided to generate suggestions."""
    original_user_query: Optional[str] = Field(default=None, description="The user's original query if the issue is an out-of-scope request.")
    original_error_message: Optional[str] = Field(default=None, description="The original error message encountered.")
    # Optional: Consider adding source_agent/tool if this info is available to FallbackHandler
    # source_tool: Optional[str] = Field(default=None, description="The tool that reported the error.")

class Suggestion(BaseModel):
    suggestion_text: str
    suggestion_type: str = Field(default="general", description="Type of suggestion (e.g., 'user_action', 'troubleshooting_step', 'clarification_request').")
    relevance_score: Optional[float] = Field(default=None, description="An estimated relevance score for the suggestion (0.0 to 1.0).")

class SuggestionGeneratorTool(BaseTool):
    name: str = "Helpful Suggestion Generator"
    description: str = (
        "Provides context-aware suggestions for users when operations fail, queries are out-of-scope, "
        "or errors occur. Suggestions are based on the error message or query content."
    )
    args_schema: Type[BaseModel] = SuggestionContextInput

    max_suggestions_config: int
    confidence_threshold_config: float

    PREDEFINED_SUGGESTIONS: Dict[str, Dict[str, Any]]
    GENERIC_SUGGESTIONS: List[Dict[str, Any]]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.max_suggestions_config = tool_config.get("max_suggestions", int(os.getenv("SUGGEN_MAX_SUGGESTIONS", 3)))
        self.confidence_threshold_config = tool_config.get("confidence_threshold", float(os.getenv("SUGGEN_CONFIDENCE_THRESHOLD", 0.5)))
        self._initialize_suggestions()
        logger.debug(f"SuggestionGeneratorTool initialized with max_suggestions: {self.max_suggestions_config}, confidence_threshold: {self.confidence_threshold_config}")

    def _initialize_suggestions(self):
        self.PREDEFINED_SUGGESTIONS = {
            "DataValidationIssue": {
                "keywords": ["invalid input", "validationerror", "missing required field", "typeerror", "valueerror", "parse error", "decodeerror", "schema validation", "incorrect format"],
                "suggestions": [
                    {"text": "Please check the format of your input. Ensure all required fields are provided correctly and match the expected data types.", "type": "user_action", "score": 0.9},
                    {"text": "The file you provided might be corrupted or in an unsupported format. Try validating the file or using a standard format (e.g., JPEG, PNG for images).", "type": "user_action", "score": 0.8},
                    {"text": "If you are using an API, ensure your request payload matches the expected schema. Consult the API documentation for details.", "type": "developer_action", "score": 0.85},
                ]
            },
            "ExternalServiceOrNetworkIssue": {
                "keywords": ["timeout", "connection refused", "dns lookup", "host not found", "sslerror", "service unavailable", "500", "502", "503", "504", "network is unreachable", "api key invalid", "authentication failed", "rate limit", "http error", "request failed"],
                "suggestions": [
                    {"text": "An external service or network connection required for this operation may be temporarily unavailable or misconfigured. Please try again in a few minutes.", "type": "user_action", "score": 0.9},
                    {"text": "If the issue persists, check your internet connection and the status page of the external service (if available).", "type": "troubleshooting_step", "score": 0.8},
                    {"text": "Ensure any required API keys for external services are correctly configured, valid, and have not expired.", "type": "admin_action", "score": 0.85},
                ]
            },
            "ConfigurationProblem": {
                "keywords": ["config file not found", "missing configuration", "invalid config value", "config error"],
                "suggestions": [
                    {"text": "There seems to be a system configuration issue. Please report this to the administrator, providing the error details.", "type": "report_issue", "score": 0.95},
                    {"text": "The application may require specific environment variables or configuration files to be set up correctly. Please check the documentation.", "type": "admin_action", "score": 0.9},
                ]
            },
            "FileSystemProblem": {
                "keywords": ["filenotfound", "no such file or directory", "permission denied", "ioerror", "could not read file", "could not write file"],
                "suggestions": [
                    {"text": "The specified file could not be found, or the application does not have permission to access it. Please verify the file path and permissions.", "type": "user_action", "score": 0.9},
                ]
            },
            "InternalToolError": {
                "keywords": ["tool execution failed", "internal logic error", "unexpected tool behavior", "agent error", "internal error", "runtime error in tool"],
                "suggestions": [
                    {"text": "An internal component encountered an issue. Retrying the operation might help. If it persists, please report the problem, noting the error message.", "type": "user_action", "score": 0.7},
                ]
            },
            "ResourceLimitProblem": {
                "keywords": ["out of memory", "memoryerror", "disk space full", "resource temporarily unavailable"],
                "suggestions": [
                    {"text": "The system is currently experiencing high load or has reached a resource limit. Please try again later.", "type": "user_action", "score": 0.8},
                    {"text": "If you are processing a very large file or request, consider trying with a smaller one.", "type": "user_action", "score": 0.75}
                ]
            },
            "OutOfScopeQuery": {
                "keywords": [], # Intentionally empty; triggered by original_user_query and no error_message
                "suggestions": [
                    {"text": "I'm designed to help with image metadata analysis. Could you try rephrasing your query to be about image properties, content, or technical details?", "type": "clarification_request", "score": 0.9},
                    {"text": "Perhaps you could ask about specific EXIF data, location information if available, or technical aspects of the image?", "type": "clarification_request", "score": 0.85},
                    {"text": "I can help with things like 'What camera was used for this image?' or 'Tell me about the exposure settings'.", "type": "example_query", "score": 0.8},
                ]
            },
            "GenericErrorFallback": {
                "keywords": [], # Intentionally empty; used if error message exists but doesn't match other categories
                "suggestions": [
                    {"text": "An unexpected issue occurred. Please try your request again. If the problem continues, consider rephrasing or simplifying your query, and note the error message provided.", "type": "user_action", "score": 0.7},
                    {"text": "You can also try being more specific about what you're trying to achieve or asking for a different type of analysis.", "type": "user_action", "score": 0.6},
                ]
            }
        }
        self.GENERIC_SUGGESTIONS = [
            {"text": "Try the operation again after a short while.", "type": "user_action", "score": 0.5},
            {"text": "Ensure your internet connection is stable if the operation involves external resources.", "type": "troubleshooting_step", "score": 0.4},
            {"text": "If the problem persists, please report the issue with the error details provided so it can be investigated.", "type": "report_issue", "score": 0.6}
        ]
        logger.debug("PREDEFINED_SUGGESTIONS and GENERIC_SUGGESTIONS have been initialized.")

    def _generate_suggestions(self, context: SuggestionContextInput) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        selected_category_key = None

        if context.original_error_message:
            error_msg_lower = context.original_error_message.lower()
            logger.debug(f"Processing error message for suggestions: {error_msg_lower[:200]}...")
            for category_key, details in self.PREDEFINED_SUGGESTIONS.items():
                if category_key in ["OutOfScopeQuery", "GenericErrorFallback"]:  # Skip special handlers
                    continue
                
                for keyword in details.get("keywords", []):
                    if keyword in error_msg_lower:
                        selected_category_key = category_key
                        logger.info(f"Error message matched category '{category_key}' with keyword '{keyword}'.")
                        break
                if selected_category_key:
                    break
            
            if selected_category_key:
                for sugg_data in self.PREDEFINED_SUGGESTIONS[selected_category_key].get("suggestions", []):
                    if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                        suggestions.append(sugg_data.copy())
            else:
                # If an error message exists but no keywords matched, use GenericErrorFallback
                logger.info("Error message did not match specific categories. Using GenericErrorFallback suggestions.")
                selected_category_key = "GenericErrorFallback" # For clarity in logging or potential future use
                for sugg_data in self.PREDEFINED_SUGGESTIONS[selected_category_key].get("suggestions", []):
                     if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                        suggestions.append(sugg_data.copy())

        elif context.original_user_query:  # No error message, but an original query implies out-of-scope
            logger.info("No error message, but original_user_query present. Using OutOfScopeQuery suggestions.")
            selected_category_key = "OutOfScopeQuery"
            for sugg_data in self.PREDEFINED_SUGGESTIONS[selected_category_key].get("suggestions", []):
                if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                    suggestions.append(sugg_data.copy())
        else:
            logger.info("No error message and no original user query. Using GenericErrorFallback as a last resort.")
            # Fallback to generic error if no context at all, though this case should be rare.
            selected_category_key = "GenericErrorFallback"
            for sugg_data in self.PREDEFINED_SUGGESTIONS[selected_category_key].get("suggestions", []):
                 if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                    suggestions.append(sugg_data.copy())

        # Add generic suggestions if needed
        current_suggestion_count = len(suggestions)
        if current_suggestion_count < self.max_suggestions_config:
            num_generic_to_add = self.max_suggestions_config - current_suggestion_count
            # Ensure no duplicate text with already added suggestions
            existing_texts = {s['suggestion_text'] for s in suggestions}
            
            shuffled_generic = random.sample(self.GENERIC_SUGGESTIONS, len(self.GENERIC_SUGGESTIONS))
            added_generic_count = 0
            for sugg_data in shuffled_generic:
                if added_generic_count >= num_generic_to_add:
                    break
                if sugg_data.get("score", 1.0) >= self.confidence_threshold_config and \
                   sugg_data['suggestion_text'] not in existing_texts:
                    suggestions.append(sugg_data.copy())
                    existing_texts.add(sugg_data['suggestion_text'])
                    added_generic_count +=1
            logger.debug(f"Added {added_generic_count} generic suggestions.")
        
        suggestions.sort(key=lambda s: s.get("relevance_score", 0.0), reverse=True)
        final_suggestions = suggestions[:self.max_suggestions_config]
        logger.debug(f"Final suggestions count: {len(final_suggestions)}")
        return final_suggestions

    def _run(self,
             original_user_query: Optional[str] = None,
             original_error_message: Optional[str] = None
            ) -> str:
        
        response: Dict[str, Any] = {"success": False, "suggestions": []}
        
        try:
            context_input_data = {
                "original_user_query": original_user_query,
                "original_error_message": original_error_message,
            }
            context = SuggestionContextInput(**context_input_data)
            logger.info(f"SuggestionGeneratorTool received context: {context.model_dump_json(indent=2)}")

            generated_suggestions_dicts = self._generate_suggestions(context)
            
            validated_suggestions = [Suggestion(**sugg).model_dump(exclude_none=True) for sugg in generated_suggestions_dicts]

            response["suggestions"] = validated_suggestions
            response["suggestions_count"] = len(validated_suggestions)
            response["input_context_processed"] = context.model_dump(exclude_none=True)
            response["success"] = True
            logger.info(f"Successfully generated {len(validated_suggestions)} suggestions.")

        except Exception as e:
            logger.exception("SuggestionGeneratorTool internal error during _run.")
            response["success"] = False
            log_context_str = str(context_input_data) if 'context_input_data' in locals() else 'Context not available'
            response["error"] = f"SuggestionGeneratorTool internal error: {str(e)}. Context: {log_context_str[:500]}" # Truncate context
            
        return json.dumps(response, default=str)

if __name__ == '__main__':
    # Basic test setup
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Mock tool_config if tools.yaml is not present or configured for these tests
    if not tool_config: # If global tool_config is empty
        tool_config.update({ # Simulate loaded config for testing
            "max_suggestions": 2,
            "confidence_threshold": 0.1
        })
        logger.info("Using mock tool_config for __main__ tests.")

    suggestion_tool = SuggestionGeneratorTool()

    test_cases = [
        {"original_error_message": "Connection timed out to external.service.com", "original_user_query": "Analyze this image."},
        {"original_error_message": "ValueError: Invalid input provided for field 'date'. Expected YYYY-MM-DD."},
        {"original_user_query": "What is the color of the sky?"}, # Out of scope
        {"original_error_message": "A very generic error occurred without specific keywords."},
        {"original_error_message": "Tool execution failed due to an internal logic error."},
        {}, # No context
    ]

    for i, case in enumerate(test_cases):
        print(f"--- Test Case {i+1} ---")
        print(f"Input: {case}")
        result_str = suggestion_tool._run(**case)
        result_json = json.loads(result_str)
        print(f"Output: {json.dumps(result_json, indent=2)}")
        print("\\n")
