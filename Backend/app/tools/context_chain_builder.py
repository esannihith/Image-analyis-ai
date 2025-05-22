from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from app.store.session_store import SessionStore, SessionStoreError
import yaml
from pathlib import Path
import os
import json

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        tool_config = yaml.safe_load(f).get("CoreTools", {}).get("ContextChainBuilder", {}).get("config", {})
except Exception:
    tool_config = {}

class ContextChainBuilderInput(BaseModel):
    session_id: str = Field(..., description="The active session identifier.")
    current_user_query: str = Field(..., description="The user's query for the current turn.")
    # Resolved references for the *current* query, typically from SessionContextManager's LLM analysis
    current_resolved_references: Dict[str, str] = Field(
        default_factory=dict, 
        description="Key-value pairs of resolved image references for the current query (e.g., {'ref_this': 'hash123'})."
    )
    # Key used to store and retrieve the list of historical turns in SessionStore
    history_context_key: str = Field(
        default="conversation_turns_history", 
        description="The session context key for storing and retrieving conversation history turns."
    )
    max_turns_to_include_override: Optional[int] = Field(
        None, 
        description="Overrides default context_depth from config if provided."
    )
    max_chars_override: Optional[int] = Field(
        None,
        description="Overrides default max_context_size (characters) from config if provided."
    )


class ContextChainBuilderTool(BaseTool):
    name: str = "Conversation Context Chain Builder"
    description: str = """
    Constructs and maintains a chain of conversation context for a session.
    It retrieves past interaction summaries, appends the current interaction (query + resolved images),
    prunes history based on depth, formats it for LLM consumption, and truncates by size.
    The updated history is stored back in the session.
    """
    args_schema: Type[BaseModel] = ContextChainBuilderInput

    # Configuration from YAML/env
    default_context_depth: int = tool_config.get("context_depth", int(os.getenv("CONTEXT_CHAIN_DEPTH", 3)))
    default_max_context_chars: int = tool_config.get("max_context_size", int(os.getenv("CONTEXT_CHAIN_MAX_SIZE_CHARS", 4096)))

    _session_store: SessionStore

    def __init__(self, session_store: Optional[SessionStore] = None, **kwargs):
        super().__init__(**kwargs)
        if session_store:
            self._session_store = session_store
        else:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                print("Warning: ContextChainBuilderTool - REDIS_URL not set. SessionStore will use default.")
            self._session_store = SessionStore(redis_url=redis_url)
            
    @property
    def session_store(self) -> SessionStore:
        if not hasattr(self, '_session_store') or self._session_store is None:
            print("Error: SessionStore not initialized in ContextChainBuilderTool. Attempting re-init.")
            self._session_store = SessionStore(redis_url=os.getenv("REDIS_URL"))
        return self._session_store

    def _format_turn_for_llm(self, turn_data: Dict[str, Any], turn_number: int) -> str:
        query = turn_data.get('query', 'N/A')
        resolved_refs = turn_data.get('resolved_images', {})
        
        ref_str_parts = []
        if resolved_refs:
            for ref_type, img_hash in resolved_refs.items():
                ref_str_parts.append(f"{ref_type.replace('ref_', '')} -> image_hash:{img_hash}")
        ref_str = f" (Images: {'; '.join(ref_str_parts)})" if ref_str_parts else ""
        
        return f"Turn {turn_number}: User asked: \"{query}\"{ref_str}"

    def _truncate_context_by_chars(self, context_str: str, max_chars: int, log: List[str]) -> str:
        if len(context_str) > max_chars:
            truncated_str = context_str[:max_chars]
            # Try to cut at a sentence boundary or newline for readability
            last_newline = truncated_str.rfind('\n')
            last_sentence = truncated_str.rfind('. ')
            cut_point = max(last_newline, last_sentence)

            if cut_point > max_chars * 0.7: # Ensure we don't cut too much
                final_str = truncated_str[:cut_point+1] # +1 to include the . or \n
            else:
                final_str = truncated_str
            log.append(f"Context truncated from {len(context_str)} to {len(final_str)} chars (max: {max_chars}).")
            return final_str + " ... [context truncated]"
        return context_str

    def _run(self, 
             session_id: str, 
             current_user_query: str, 
             current_resolved_references: Dict[str, str], 
             history_context_key: str = "conversation_turns_history",
             max_turns_to_include_override: Optional[int] = None,
             max_chars_override: Optional[int] = None
            ) -> str:
        
        log: List[str] = [f"ContextChainBuilderTool started for session: {session_id}"]
        response_payload: Dict[str, Any]

        context_depth = max_turns_to_include_override if max_turns_to_include_override is not None else self.default_context_depth
        max_chars = max_chars_override if max_chars_override is not None else self.default_max_context_chars
        log.append(f"Using context_depth: {context_depth}, max_chars: {max_chars}")

        try:
            # 1. Fetch historical context
            historical_turns: List[Dict[str, Any]] = self.session_store.get_session_context(
                session_id, history_context_key
            ) or []
            if not isinstance(historical_turns, list): # Ensure it's a list
                log.append(f"Warning: Historical context for key '{history_context_key}' was not a list, re-initializing.")
                historical_turns = []
            log.append(f"Fetched {len(historical_turns)} historical turns from key '{history_context_key}'.")

            # 2. Construct current turn summary
            current_turn_summary = {
                "query": current_user_query,
                "resolved_images": current_resolved_references, # these are {ref_type: hash}
                "timestamp": datetime.utcnow().isoformat()
            }
            log.append(f"Current turn summary: {current_turn_summary}")

            # 3. Append and Prune History
            updated_historical_turns = historical_turns + [current_turn_summary]
            if len(updated_historical_turns) > context_depth:
                num_to_prune = len(updated_historical_turns) - context_depth
                updated_historical_turns = updated_historical_turns[num_to_prune:]
                log.append(f"Pruned {num_to_prune} oldest turns to maintain depth of {context_depth}.")
            
            # 4. Store Updated Historical Context (before formatting for output to save the full history)
            self.session_store.update_session_context(session_id, history_context_key, updated_historical_turns)
            log.append(f"Stored updated history ({len(updated_historical_turns)} turns) to key '{history_context_key}'.")

            # 5. Format the Context Package for LLM consumption (most recent `context_depth` turns)
            # We use updated_historical_turns which is already pruned by depth for formatting
            formatted_context_parts = []
            # Iterate in reverse to format most recent turns first if needed, but here we format all pruned turns
            # Turn numbers are relative to the current window
            for i, turn_data in enumerate(updated_historical_turns):
                # For display, let's use 1-based indexing for "Turn X of Y"
                # Or, more simply, just format each turn. The LLM will see the sequence.
                formatted_context_parts.append(self._format_turn_for_llm(turn_data, i + 1)) 
            
            final_context_str = "\n".join(formatted_context_parts)
            log.append(f"Formatted context string (pre-truncation): {final_context_str}")

            # 6. Truncate by character size
            final_context_str_truncated = self._truncate_context_by_chars(final_context_str, max_chars, log)
            
            response_payload = {
                "success": True,
                "built_context_string": final_context_str_truncated,
                "total_turns_in_history": len(updated_historical_turns),
                "log": log
            }

        except SessionStoreError as e:
            log.append(f"SessionStoreError: {e}")
            response_payload = {"success": False, "error": f"SessionStore Error ({e.code}): {str(e)}", "log": log}
        except Exception as e:
            log.append(f"Unexpected error: {e}")
            import traceback
            log.append(traceback.format_exc(limit=3))
            response_payload = {"success": False, "error": f"Unexpected error: {str(e)}", "log": log}
            
        return json.dumps(response_payload, default=str)
