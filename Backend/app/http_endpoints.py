from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import uuid
import json
from app.crew import ImageMetadataConversationalAssistantCrew
from app.store.session_store import SessionStore

router = APIRouter()

crew = ImageMetadataConversationalAssistantCrew()
session_store = SessionStore()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_image(session_id: str = Form(...), file: UploadFile = File(...)):
    try:
        # Get file extension, default to .jpg if none
        filename = file.filename or "uploaded_file"
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg"
            
        # Generate unique ID with extension
        image_id = str(uuid.uuid4()) + ext
        file_path = os.path.join(UPLOAD_DIR, image_id)
        
        # Ensure uploads directory exists
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        # Write file to disk
        with open(file_path, "wb") as f:
            content = await file.read()
            if not content:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Empty file uploaded"}
                )
            f.write(content)
            
        # Update session store
        session_store.touch_session(session_id)
        session_store.set_metadata(session_id, image_id, {
            "file_path": file_path,
            "filename": filename,
            "uploaded_at": str(uuid.uuid1()),
            "size": len(content)
        })
        
        print(f"Image uploaded successfully: {image_id} (Session: {session_id})")
        return {
            "success": True,
            "image_id": image_id,
            "file_path": file_path,
            "session_id": session_id,
            "filename": filename
        }
    except Exception as e:
        print(f"Error uploading image: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Upload failed: {str(e)}"}
        )

@router.get("/download_csv/{session_id}")
async def download_csv(session_id: str):
    csv_tool = crew.CSVExportAgent().tools[0]
    csv_result = csv_tool._run(session_id)
    try:
        csv_data = json.loads(csv_result)
    except Exception:
        return JSONResponse(status_code=500, content={"success": False, "error": "CSV export failed (invalid JSON)."})
    if not csv_data.get("success"):
        return JSONResponse(status_code=404, content={"success": False, "error": csv_data.get("error", "CSV export failed.")})
    csv_content = csv_data.get("csv", "")
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=metadata_{session_id}.csv"}
    )

# Admin/test endpoints
@router.get("/session/{session_id}")
async def get_session_metadata(session_id: str):
    data = session_store.get_all_metadata(session_id)
    return {"success": True, "metadata": data}

@router.get("/health")
async def health_check():
    return {"success": True, "status": "ok"}

@router.get("/uploads/{image_id}")
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
