import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import random

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("ErrorTools", {}).get("SuggestionGenerator", {}).get("config", {})
except Exception:
    tool_config = {}

# Input can be complex, using the output of ErrorClassifier or raw query
class SuggestionContextInput(BaseModel):
    """Context provided to generate suggestions."""
    # For out-of-scope queries
    original_user_query: Optional[str] = Field(None, description="The user's original query if the issue is an out-of-scope request.")
    
    # For classified errors (typically from ErrorClassifierTool)
    error_category: Optional[str] = Field(None, description="Category of the error (e.g., 'ExternalServiceError', 'DataValidationError').")
    assigned_severity: Optional[str] = Field(None, description="Severity of the error (e.g., 'critical', 'error').")
    original_error_message: Optional[str] = Field(None, description="The original error message encountered.")
    # session_id: Optional[str] = Field(None, description="Optional session ID for context.")


class Suggestion(BaseModel):
    suggestion_text: str
    suggestion_type: str = Field("general", description="Type of suggestion (e.g., 'user_action', 'troubleshooting_step', 'clarification_request').")
    relevance_score: Optional[float] = Field(None, description="An estimated relevance score for the suggestion (0.0 to 1.0).")


class SuggestionGeneratorTool(BaseTool):
    name: str = "Helpful Suggestion Generator"
    description: str = (
        "Provides context-aware suggestions for users or administrators when operations fail, "
        "queries are out-of-scope, or errors occur. Suggestions are based on error categories or query content."
    )
    args_schema: Type[BaseModel] = SuggestionContextInput # Input is the context itself

    # Configuration from YAML/env
    max_suggestions_config: int = tool_config.get("max_suggestions", int(os.getenv("SUGGEN_MAX_SUGGESTIONS", 3))) # Changed from 5 to 3 to match user files
    # Confidence threshold might be used to filter suggestions if they have scores.
    confidence_threshold_config: float = tool_config.get("confidence_threshold", float(os.getenv("SUGGEN_CONFIDENCE_THRESHOLD", 0.5)))


    # Predefined suggestions based on error categories or query types.
    # Each suggestion can have a base relevance score.
    PREDEFINED_SUGGESTIONS: Dict[str, List[Dict[str, Any]]] = {
        "DataValidationError": [
            {"text": "Please check the format of your input. Ensure all required fields are provided correctly.", "type": "user_action", "score": 0.9},
            {"text": "The file you provided might be corrupted or in an unsupported format. Try validating the file or using a standard format (e.g., JPEG, PNG for images).", "type": "user_action", "score": 0.8},
            {"text": "If you are using an API, ensure your request payload matches the expected schema.", "type": "developer_action", "score": 0.85},
        ],
        "ExternalServiceError": [
            {"text": "An external service required for this operation may be temporarily unavailable. Please try again in a few minutes.", "type": "user_action", "score": 0.9},
            {"text": "If the issue persists, check the status page of the external service (if available) or contact support.", "type": "troubleshooting_step", "score": 0.8},
            {"text": "Ensure your API keys for external services are correctly configured and have not expired.", "type": "admin_action", "score": 0.85},
        ],
        "ConfigurationError": [
            {"text": "There seems to be a system configuration issue. Please report this to the administrator.", "type": "report_issue", "score": 0.95},
            {"text": "The application may require specific environment variables or configuration files to be set up correctly.", "type": "admin_action", "score": 0.9},
        ],
        "FileSystemError": [
            {"text": "The specified file could not be found or accessed. Please verify the file path and permissions.", "type": "user_action", "score": 0.9},
        ],
        "ToolExecutionError": [
            {"text": "An internal tool encountered an issue. Retrying the operation might help. If it persists, please report the problem.", "type": "user_action", "score": 0.7},
        ],
        "ResourceLimitError": [
             {"text": "The system is currently experiencing high load or has reached a resource limit. Please try again later.", "type": "user_action", "score": 0.8},
             {"text": "If you are processing a very large file or request, try with a smaller one.", "type": "user_action", "score": 0.75}
        ],
        "UnknownError": [
            {"text": "An unexpected issue occurred. Please try your request again. If the problem continues, consider rephrasing or simplifying your query.", "type": "user_action", "score": 0.7},
            {"text": "You can also try being more specific about what you're trying to achieve.", "type": "user_action", "score": 0.6},
        ],
        "UnclassifiedError": [ # Fallback for errors not specifically categorized by ErrorClassifier
            {"text": "An unclassified error occurred. Try simplifying your request or check your input. If the problem continues, please note the error message.", "type": "user_action", "score": 0.6},
        ],
        "OutOfScopeQuery": [ # Suggestions for when the user's query is out of scope
            {"text": "I'm designed to help with image metadata analysis. Could you try rephrasing your query to be about image properties, content, or technical details?", "type": "clarification_request", "score": 0.9},
            {"text": "Perhaps you could ask about specific EXIF data, location information if available, or technical aspects of the image?", "type": "clarification_request", "score": 0.85},
            {"text": "I can help with things like 'What camera was used for this image?' or 'Tell me about the exposure settings'.", "type": "example_query", "score": 0.8},
        ]
    }
    GENERIC_SUGGESTIONS = [
        {"text": "Try the operation again after a short while.", "type": "user_action", "score": 0.5},
        {"text": "Ensure your internet connection is stable.", "type": "troubleshooting_step", "score": 0.4},
        {"text": "If the problem persists, please report the issue with the error details.", "type": "report_issue", "score": 0.6}
    ]


    def _generate_suggestions(self, context: SuggestionContextInput) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        
        context_key = "UnknownError" # Default context
        
        if context.error_category:
            context_key = context.error_category
        elif context.original_user_query: # If no error, but an out-of-scope query
            # Simple heuristic for out-of-scope: if no error category, assume original query needs help
            # A more sophisticated out-of-scope detection would happen before calling this tool.
            # This tool assumes if error_category is None, it's about the original_user_query.
            context_key = "OutOfScopeQuery" 
            # Could add more NLP-based query analysis here to pick better suggestions for queries.

        # Add suggestions specific to the context (error category or query type)
        if context_key in self.PREDEFINED_SUGGESTIONS:
            for sugg_data in self.PREDEFINED_SUGGESTIONS[context_key]:
                if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                    suggestions.append({
                        "suggestion_text": sugg_data["text"],
                        "suggestion_type": sugg_data.get("type", "general"),
                        "relevance_score": sugg_data.get("score")
                    })
        
        # Add some generic suggestions if we don't have enough specifics, or always add a few
        if not suggestions or len(suggestions) < self.max_suggestions_config:
            num_generic_to_add = self.max_suggestions_config - len(suggestions)
            # Shuffle generic to provide variety if called multiple times for similar non-specific issues
            shuffled_generic = random.sample(self.GENERIC_SUGGESTIONS, len(self.GENERIC_SUGGESTIONS))
            for i in range(min(num_generic_to_add, len(shuffled_generic))):
                sugg_data = shuffled_generic[i]
                if sugg_data.get("score", 1.0) >= self.confidence_threshold_config:
                     # Avoid adding duplicate generic suggestions if already present by text
                    if not any(s['suggestion_text'] == sugg_data['text'] for s in suggestions):
                        suggestions.append({
                            "suggestion_text": sugg_data["text"],
                            "suggestion_type": sugg_data.get("type", "general"),
                            "relevance_score": sugg_data.get("score")
                        })
        
        # Sort by relevance score (descending) and limit to max_suggestions_config
        suggestions.sort(key=lambda s: s.get("relevance_score", 0.0), reverse=True)
        return suggestions[:self.max_suggestions_config]


    def _run(self, 
             original_user_query: Optional[str] = None, 
             error_category: Optional[str] = None, 
             assigned_severity: Optional[str] = None, 
             original_error_message: Optional[str] = None) -> str:
        
        response: Dict[str, Any] = {"success": False, "suggestions": []}
        
        try:
            # Construct the context input object
            context_input_data = {
                "original_user_query": original_user_query,
                "error_category": error_category,
                "assigned_severity": assigned_severity,
                "original_error_message": original_error_message
            }
            # Remove None values to avoid Pydantic validation issues if a field is truly optional
            # and not just None by default in the model.
            # However, our Pydantic model SuggestionContextInput uses Optional, so None is fine.
            
            context = SuggestionContextInput(**context_input_data)

            generated_suggestions_dicts = self._generate_suggestions(context)
            
            # Validate output suggestions with Pydantic model
            validated_suggestions = [Suggestion(**sugg).model_dump(exclude_none=True) for sugg in generated_suggestions_dicts]

            response["suggestions"] = validated_suggestions
            response["suggestions_count"] = len(validated_suggestions)
            response["input_context_processed"] = context.model_dump(exclude_none=True)
            response["success"] = True

        except Exception as e:
            response["success"] = False
            response["error"] = f"SuggestionGeneratorTool internal error: {str(e)}. Context: {str(context_input_data if 'context_input_data' in locals() else 'not available')[:500]}"
            # traceback.print_exc() # For server-side logging
            
        return json.dumps(response, default=str)
