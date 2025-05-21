# app/tools/session_retrieval_tool.py
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.tools.base_tool import BaseImageMetadataTool, BaseInput

class SessionRetrievalInput(BaseInput):
    context_type: str = Field(
        ..., 
        description="Type of context to retrieve (e.g., 'image_sequence', 'conversation_history', 'user_preferences')"
    )
    limit: Optional[int] = Field(
        10, 
        description="Maximum number of items to retrieve"
    )

class SessionRetrievalTool(BaseImageMetadataTool):
    name: str = "Session Retrieval Tool"
    description: str = """
    Retrieves session context, including conversation history, image upload sequence, 
    and user preferences. Essential for maintaining continuity across multiple user 
    interactions.
    """
    args_schema: Type[BaseModel] = SessionRetrievalInput
    
    def _run(self, session_id: str, image_hash: str, context_type: str, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieve session context data for the specified context type
        
        Args:
            session_id: The session identifier
            image_hash: Current image being discussed
            context_type: Type of context to retrieve
            limit: Maximum number of items to return
            
        Returns:
            Dictionary with context data and success indicator
        """
        try:
            if context_type == "image_sequence":
                # Get all images in upload order
                images = self._get_session_images(session_id)
                return self._format_success_response(
                    images=images[:limit],
                    total_count=len(images),
                    current_index=next((i for i, img in enumerate(images) if img.get("hash") == image_hash), -1)
                )
                
            elif context_type == "conversation_history":
                # Get recent conversation history
                history = self._get_session_context(session_id, "conversation_history") or []
                return self._format_success_response(
                    history=history[-limit:],
                    total_exchanges=len(history)
                )
                
            elif context_type == "user_preferences":
                # Get stored user preferences
                preferences = self._get_session_context(session_id, "user_preferences") or {}
                return self._format_success_response(preferences=preferences)
                
            else:
                # Get generic context by key
                context = self._get_session_context(session_id, context_type)
                if context is None:
                    return self._format_error_response(f"Context type '{context_type}' not found in session")
                return self._format_success_response(context=context)
                
        except Exception as e:
            return self._format_error_response(f"Failed to retrieve session context: {str(e)}")