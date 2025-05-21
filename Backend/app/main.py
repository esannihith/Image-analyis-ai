#!/usr/bin/env python
"""
Main FastAPI server for the Image Metadata Conversational Assistant backend.
Handles image uploads, chat requests, CSV download, and session management.
Integrates with CrewAI pipeline and Redis-backed session store.
"""
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
import os
import sys
import uuid
import json
from app.crew import ImageMetadataConversationalAssistantCrew
from app.store.session_store import SessionStore
import socketio
from fastapi import WebSocket
from app.http_endpoints import router as http_router
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

# Register HTTP endpoints
app.include_router(http_router)

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Mount Socket.IO as ASGI app
app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
