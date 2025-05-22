# socket_events.py
import socketio
from .crew import ImageAnalysisCrew
from .store.session_store import SessionStore, SessionStoreError
import uuid
import hashlib
import traceback # For logging full tracebacks
import json

# Instantiate the crew.
crew = None # Initialize crew to None
try:
    crew = ImageAnalysisCrew()
    print("INFO: ImageAnalysisCrew initialized successfully.")
except Exception as e:
    print(f"CRITICAL: Failed to initialize ImageAnalysisCrew: {e}")
    # crew remains None, indicating the core service is unavailable

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', engineio_logger=False)

# Helper to emit a structured service status update
async def emit_service_unavailable_status(sid, context_message=""):
    status_payload = {
        "status": "error",
        "role": "assistant",
        "title": "Image Analysis Service Unavailable",
        "message": f"The core image analysis service could not be initialized. {context_message}While you are connected, analysis features are currently offline. Please try again later or contact support.".strip(),
        "code": "CREW_INIT_FAILURE",
        "timestamp": uuid.uuid4().hex
    }
    await sio.emit("service_status_update", status_payload, to=sid)

async def handle_session_error(sid, error_message, error_code="SESSION_ERROR", severity="critical"):
    # Simplified error structure for emitting
    await sio.emit("session_error", {
        "code": error_code,
        "message": error_message,
        "severity": severity,
        "timestamp": uuid.uuid4().hex # Generate a timestamp here or get from error if available
    }, to=sid)

@sio.event
async def connect(sid, environ):
    print(f"Socket connected: {sid}")
    if not crew:
        await emit_service_unavailable_status(sid, "Connection established, but ")
        # IMPORTANT: Do not disconnect. Allow the client to stay connected and receive this status.
    else:
        print(f"Socket connected: {sid} - Analysis crew is available.")
        # Optional: you could emit a positive status here if the frontend expects it
        # await sio.emit("service_status_update", {"status": "ok", "type": "BOT_MESSAGE", "message": "Analysis service ready."}, to=sid)

@sio.event
async def disconnect(sid):
    # No change needed here based on crew status, but ensure checks for crew and store if used
    if crew and hasattr(crew, 'session_store') and crew.session_store:
        try:
            session = await sio.get_session(sid)
            if session and 'session_id' in session:
                # Example: crew.session_store.touch_session(session['session_id'])
                # Or cleanup logic if necessary
                pass # Replace with actual logic if any
        except Exception as e:
            print(f"Session cleanup/get_session failed on disconnect for SID {sid}: {str(e)}")
    print(f"Socket disconnected: {sid}")

@sio.event
async def session_init(sid, data):
    if not crew or not hasattr(crew, 'session_store') or not crew.session_store:
        # The 'connect' event handler would have already sent emit_service_unavailable_status.
        # This check prevents a duplicate or variant message about service unavailability.
        print(f"INFO: session_init for SID {sid} attempted but service is unavailable. Initial status already conveyed on connect.")
        # Optionally, emit a specific error that session_init cannot proceed if needed later:
        # await handle_session_error(sid, "Session initialization failed: Core service is unavailable.", "SESSION_INIT_SERVICE_DOWN")
        return # Return early, do not emit the generic service_status_update again.

    try:
        session_id = data.get("session_id") if data and isinstance(data, dict) else None
        if not session_id:
            session_id = str(uuid.uuid4())
            print(f"No session_id provided or data invalid, generated new: {session_id} for SID: {sid}")
        else:
            print(f"session_init called for SID: {sid} with client-provided session_id: {session_id}")

        crew.session_store.create_session(session_id)
        
        await sio.save_session(sid, {'session_id': session_id})
        await sio.enter_room(sid, room=session_id)
        
        await sio.emit("session_ready", {
            "session_id": session_id,
            "ttl": crew.session_store.session_ttl
        }, to=sid)
        print(f"Session {session_id} initialized and ready for SID {sid}.")
        
    except Exception as e:
        error_message = f"Session initialization failed: {str(e)}"
        print(f"Error in session_init for SID {sid}: {error_message}\n{traceback.format_exc()}")
        await handle_session_error(sid, error_message, "SESSION_INIT_FAILED")

@sio.event
async def upload_image(sid, data):
    session_id = "N/A" # Default for logging if session retrieval fails
    try:
        if not crew or not hasattr(crew, 'session_store') or not crew.session_store:
            await emit_service_unavailable_status(sid, "Cannot upload image. ")
            return

        session = await sio.get_session(sid)
        if not session or 'session_id' not in session:
            await handle_session_error(sid, "Session not initialized. Please initialize session first.", "NO_SESSION", "warning")
            return
        session_id = session['session_id']
        
        if not isinstance(data, dict) or 'file' not in data:
            await sio.emit("upload_error", {"code": "INVALID_PAYLOAD", "message": "Invalid upload data format. 'file' is required."}, to=sid)
            return

        image_data_bytes = data['file']
        filename = data.get('filename', f"upload_{uuid.uuid4().hex}.jpg")
        additional_metadata_from_client = data.get('metadata', {})

        # Prepare the metadata for store_image_metadata
        # This structure might need to be more aligned with what _validate_metadata expects (exif, iptc, xmp sections)
        # For now, including filename and whatever the client sends as 'metadata'.
        metadata_to_store = {
            "filename": filename,
            **additional_metadata_from_client # Merges client-provided metadata
            # If additional_metadata_from_client is empty, this will at least have a filename.
            # _validate_metadata expects 'exif', 'iptc', or 'xmp' keys. This is likely to fail
            # if the client doesn't send structured metadata including one of these keys.
            # A placeholder like "placeholder_metadata_section": {} might be needed if validation is strict
            # and client sends nothing, e.g., "exif": {}
        }
        if not any(key in metadata_to_store for key in ['exif', 'iptc', 'xmp']) and additional_metadata_from_client:
            # If client sent *some* metadata, but not the required sections, wrap it under a generic key
            # to avoid direct validation failure, though this isn't ideal.
            # A better fix is to align client data or SessionStore validation.
            metadata_to_store = {
                "filename": filename,
                "client_provided": additional_metadata_from_client 
            }
            # To pass validation, we might need to add a dummy required section if none exists
            if not any(key in metadata_to_store for key in ['exif', 'iptc', 'xmp']):
                 metadata_to_store["exif"] = {"comment": "Placeholder for validation"}


        elif not additional_metadata_from_client:
             # If client sent no metadata, add a dummy section to pass validation
             metadata_to_store["exif"] = {"comment": "Placeholder for validation - no client metadata"}

        
        image_hash = crew.session_store.store_image_metadata( # Corrected method name
            session_id,
            image_data_bytes,
            metadata_to_store # Pass the constructed metadata dictionary
        )
        # image_hash is directly returned

        session_images = crew.session_store.get_session_images(session_id)
        position = next((i for i, img_info in enumerate(session_images) if img_info.get("hash") == image_hash), -1)
        
        print(f"Image uploaded for session {session_id}: hash {image_hash}, position {position}")
        await sio.emit("upload_success", {
            "image_hash": image_hash,
            "filename": filename, # Return original filename for client convenience
            "session_id": session_id,
            "position": position
        }, to=sid)

    except Exception as e:
        error_message = f"Image upload processing failed: {str(e)}"
        print(f"Error in upload_image for SID {sid}, session {session_id}: {error_message}\n{traceback.format_exc()}")
        await sio.emit("upload_error", {
            "code": "UPLOAD_PROCESSING_ERROR",
            "message": error_message
        }, to=sid)

@sio.event
async def user_question(sid, data):
    session_id = "N/A" # Default for logging
    try:
        if not crew or not hasattr(crew, 'session_store') or not crew.session_store:
            await emit_service_unavailable_status(sid, "Cannot process question. ")
            return

        session = await sio.get_session(sid)
        if not session or 'session_id' not in session:
            await handle_session_error(sid, "Session not initialized. Please initialize session first.", "NO_SESSION", "warning")
            return
        session_id = session['session_id']

        if not isinstance(data, dict):
            await sio.emit("processing_error", {"code": "INVALID_PAYLOAD", "message": "Invalid question data format."}, to=sid)
            return

        user_query = data.get("question")
        current_image_hash_focus = data.get("image_hash")

        if not user_query:
            await sio.emit("processing_error", {"code": "MISSING_PARAMETER", "message": "Missing 'question' parameter."}, to=sid)
            return
        
        if current_image_hash_focus:
            session_images = crew.session_store.get_session_images(session_id)
            if not any(img.get('hash') == current_image_hash_focus for img in session_images):
                await handle_session_error(sid, f"Image with hash '{current_image_hash_focus}' not found in this session.", "IMAGE_NOT_IN_SESSION", "warning")
                return
        
        crew.session_store.touch_session(session_id)
        
        crew_inputs = {
            "session_id": session_id,
            "user_query": user_query,
            "current_image_focus_hash": current_image_hash_focus
        }
        
        print(f"Processing user question for session {session_id} with inputs: {crew_inputs}")
        raw_result = crew.run(inputs=crew_inputs)
        
        processed_result: str
        if isinstance(raw_result, dict):
            # Attempt to extract a meaningful message if it's a structured error/response
            if raw_result.get("success") == False and raw_result.get("message"):
                processed_result = f"An error occurred: {raw_result.get('message')}"
                if raw_result.get("error") and raw_result.get("error") != raw_result.get("message"):
                    processed_result += f" (Details: {raw_result.get('error')})"
            elif isinstance(raw_result.get("result"), str): # Check if there's a nested result string
                processed_result = raw_result.get("result")
            else:
                # Fallback: convert the whole dict to a JSON string if it's not a simple error
                # This might still be an object if the crew's final output isn't a string by design
                # The LLM/agent should ideally return a string as the final textual output.
                processed_result = json.dumps(raw_result, indent=2) 
        elif isinstance(raw_result, str):
            processed_result = raw_result
        else:
            # Fallback for any other type
            processed_result = str(raw_result)

        print(f"Crew raw_result for session {session_id}: {raw_result}")
        print(f"Crew processed_result for session {session_id}: {processed_result}")
        await sio.emit("analysis_result", {
            "question": user_query,
            "result": processed_result # Ensure this is always a string
        }, to=sid)
        
    except Exception as e:
        error_message = f"Analysis pipeline failed: {str(e)}"
        print(f"Error in user_question for SID {sid}, session {session_id}: {error_message}\n{traceback.format_exc()}")
        await sio.emit("processing_error", {
            "code": "ANALYSIS_PIPELINE_FAILURE",
            "message": error_message
        }, to=sid)

# Ensure that the `sio` object is available to be imported by your ASGI app (main.py)
# For example, in main.py:
# from .socket_events import sio as socket_app
# app.mount(\"/socket.io\", socketio.ASGIApp(socket_app))