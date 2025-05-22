#!/usr/bin/env python
"""
Main FastAPI server for the Image Metadata Conversational Assistant backend.
Provides WebSocket-based communication with frontend and basic health check.
All image handling and metadata operations are handled via WebSocket events.
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import socketio
from app.socket_events import sio

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Add health check endpoint
@app.get("/health")
async def health_check():
    return {"success": True, "status": "ok"}

# Serve uploaded images directly
@app.get("/uploads/{image_id}")
async def get_image(image_id: str):
    file_path = os.path.join(UPLOAD_DIR, image_id)
    
    if not os.path.exists(file_path):
        print(f"Image not found: {image_id}, path: {file_path}")
        return JSONResponse(
            status_code=404, 
            content={"success": False, "error": f"Image not found: {image_id}"}
        )
        
    try:
        # Determine media type based on file extension
        from fastapi.responses import FileResponse
        ext = os.path.splitext(image_id)[1].lower()
        media_type = None
        if ext in ['.jpg', '.jpeg']:
            media_type = 'image/jpeg'
        elif ext == '.png':
            media_type = 'image/png'
        elif ext == '.gif':
            media_type = 'image/gif'
        elif ext == '.webp':
            media_type = 'image/webp'
            
        # Return the file
        return FileResponse(
            file_path,
            media_type=media_type,
            filename=image_id
        )
    except Exception as e:
        print(f"Error serving image {image_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error serving image: {str(e)}"}
        )

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Mount Socket.IO as ASGI app
app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
    
# Entry point functions for pyproject.toml scripts
def run():
    """Entry point for starting the server"""
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
    
def train():
    """Entry point for training functionality"""
    from app.crew import ImageMetadataConversationalAssistantCrew
    crew = ImageMetadataConversationalAssistantCrew()
    return crew.train()
    
def replay():
    """Entry point for replay functionality"""
    from app.crew import ImageMetadataConversationalAssistantCrew
    crew = ImageMetadataConversationalAssistantCrew()
    return crew.replay()
    
def test():
    """Entry point for running tests"""
    print("Running tests...")
    import unittest
    tests = unittest.TestLoader().discover('tests')
    unittest.TextTestRunner().run(tests)
