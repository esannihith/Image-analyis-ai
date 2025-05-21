# app/tools/base_tool.py
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Type
from app.store.session_store import SessionStore

class BaseInput(BaseModel):
    """Base input model for all image metadata tools"""
    session_id: str = Field(
        ..., 
        description="Session ID for the user session"
    )
    image_hash: str = Field(
        ..., 
        description="Content hash of the image to analyze"
    )

class BaseImageMetadataTool(BaseTool):
    """
    Base class for all image metadata analysis tools.
    
    Provides common functionality:
    - Access to session store
    - Standard error handling
    - Consistent output formatting
    - Metadata retrieval helpers
    """
    name: str = "Base Image Metadata Tool"
    description: str = "Base class for all image metadata tools"
    
    def __init__(self):
        super().__init__()
        self.session_store = SessionStore()
        
    def _get_metadata(self, session_id: str, image_hash: str) -> Dict[str, Any]:
        """Helper to retrieve metadata with error handling"""
        try:
            return self.session_store.get_image_metadata(session_id, image_hash)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to retrieve metadata: {str(e)}"
            }
            
    def _get_session_images(self, session_id: str) -> List[Dict[str, Any]]:
        """Helper to retrieve all images for a session"""
        try:
            return self.session_store.get_session_images(session_id)
        except Exception as e:
            return []
            
    def _get_session_context(self, session_id: str, key: str) -> Any:
        """Helper to retrieve session context data"""
        try:
            return self.session_store.get_session_context(session_id, key)
        except Exception as e:
            return None
            
    def _update_session_context(self, session_id: str, key: str, data: Any) -> None:
        """Helper to store session context data"""
        try:
            self.session_store.update_session_context(session_id, key, data)
        except Exception as e:
            pass  # Silently fail on context updates
    
    def _format_success_response(self, **kwargs) -> Dict[str, Any]:
        """Format a successful response with consistent structure"""
        return {"success": True, "error": None, **kwargs}
        
    def _format_error_response(self, error: str) -> Dict[str, Any]:
        """Format an error response with consistent structure"""
        return {"success": False, "error": error}
