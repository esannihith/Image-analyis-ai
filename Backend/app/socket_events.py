# socket_events.py
import socketio
from .crew import ImageAnalysisCrew
from .store.session_store import SessionStore, SessionStoreError
import uuid
import hashlib

# Instantiate the crew. This will also initialize its own SessionStore.
# Ensure environment variables for LLM, Redis, VisualCrossing API key are set.
try:
    crew = ImageAnalysisCrew() 
    # Access session_store via the crew instance if needed directly in socket events
    # For example: crew.session_store.create_session(...)
except Exception as e:
    print(f"CRITICAL: Failed to initialize ImageAnalysisCrew: {e}")
    # Handle this critical failure appropriately - the app might not be able to start.
    # For now, we'll let it raise if crew init fails, or define a fallback crew.
    crew = None # Or some NoOpCrew

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', engineio_logger=True)

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
        await sio.emit("server_error", {"message": "Image analysis service is currently unavailable."}, to=sid)
        await sio.disconnect(sid) # Optional: disconnect if crew failed to init

@sio.event
async def disconnect(sid):
    if crew and crew.session_store: # Check if crew and its store are available
        try:
            session = await sio.get_session(sid)
            if session and 'session_id' in session:
                crew.session_store.touch_session(session['session_id'])
        except Exception as e: # Catch generic exception from get_session or touch_session
            print(f"Session touch/get_session failed on disconnect for SID {sid}: {str(e)}")
    print(f"Socket disconnected: {sid}")

@sio.event
async def session_init(sid, data):
    if not crew or not crew.session_store:
        await sio.emit("server_error", {"message": "Image analysis service is currently unavailable for session init."}, to=sid)
        return

    try:
        session_id = data.get("session_id") if data and isinstance(data, dict) else None
        if not session_id: # Create a new session_id if not provided or if data is not a dict
            session_id = str(uuid.uuid4())
            print(f"No session_id provided by client or data is not dict, generated new: {session_id} for SID: {sid}")
        else:
            print(f"session_init called for SID: {sid} with client-provided session_id: {session_id}")

        crew.session_store.create_session(session_id) # Use crew's session_store
        
        await sio.save_session(sid, {
            'session_id': session_id
            # 'active_image': None # No longer needed here, SessionContextManager handles focus
        })
        # It's good practice to have client join a room named after their session_id
        # This allows targeted emits to all connections for that session if needed later.
        await sio.enter_room(sid, room=session_id) 
        
        await sio.emit("session_ready", {
            "session_id": session_id,
            "ttl": crew.session_store.session_ttl 
        }, to=sid)
        print(f"Session {session_id} initialized and ready for SID {sid}.")
        
    # Catch SessionStoreError specifically if it's well-defined with code, message etc.
    # For now, SessionStore might raise generic exceptions or custom ones.
    except Exception as e: # Catch generic exception from create_session
        error_message = f"Session initialization failed: {str(e)}"
        print(f"Error in session_init for SID {sid}: {error_message}")
        await handle_session_error(sid, error_message, "SESSION_INIT_FAILED")


@sio.event
async def upload_image(sid, data):
    if not crew or not crew.session_store:
        await sio.emit("server_error", {"message": "Image analysis service is currently unavailable for upload."}, to=sid)
        return

    try:
        session = await sio.get_session(sid)
        if not session or 'session_id' not in session:
            await handle_session_error(sid, "Session not initialized. Please initialize session first.", "NO_SESSION", "warning")
            return
            
        session_id = session['session_id']
        
        if not isinstance(data, dict) or 'file' not in data:
            await sio.emit("upload_error", {"code": "INVALID_PAYLOAD", "message": "Invalid upload data format. 'file' is required."}, to=sid)
            return

        image_data_bytes = data['file'] # Assuming this is bytes
        # filename and other metadata can be passed if available from client
        filename = data.get('filename', f"upload_{uuid.uuid4().hex}.jpg") # Default filename
        additional_metadata = data.get('metadata', {}) # e.g., client-side extracted GPS, notes

        # Store image using SessionStore.
        # store_image_data should handle hash generation and return it.
        # It should also store the provided filename and any additional_metadata.
        # Let's assume store_image_data replaces store_image_metadata for clarity
        image_details = crew.session_store.store_image_data(
            session_id,
            image_data_bytes,
            filename,
            additional_client_metadata=additional_metadata # Pass along client metadata
        )
        image_hash = image_details["hash"] # Assuming store_image_data returns a dict with at least 'hash'
        
        # SessionStore's get_session_images should return images in upload order.
        # No need to explicitly manage "upload_sequence" here if SessionStore does it.
        
        session_images = crew.session_store.get_session_images(session_id)
        position = -1
        for i, img_info in enumerate(session_images):
            if img_info.get("hash") == image_hash:
                position = i
                break
        
        print(f"Image uploaded for session {session_id}: hash {image_hash}, position {position}")
        await sio.emit("upload_success", {
            "image_hash": image_hash,
            "filename": image_details.get("filename", filename), # Return stored filename
            "position": position # 0-indexed
        }, to=sid)

    except Exception as e: # Catch generic exception
        error_message = f"Image upload processing failed: {str(e)}"
        print(f"Error in upload_image for SID {sid}, session {session_id if 'session_id' in locals() else 'N/A'}: {error_message}")
        import traceback
        traceback.print_exc()
        await sio.emit("upload_error", {
            "code": "UPLOAD_PROCESSING_ERROR",
            "message": error_message
        }, to=sid)


@sio.event
async def user_question(sid, data):
    if not crew or not crew.session_store:
        await sio.emit("server_error", {"message": "Image analysis service is currently unavailable for questions."}, to=sid)
        return

    try:
        session = await sio.get_session(sid)
        if not session or 'session_id' not in session:
            await handle_session_error(sid, "Session not initialized. Please initialize session first.", "NO_SESSION", "warning")
            return
            
        session_id = session['session_id']

        if not isinstance(data, dict):
            await sio.emit("processing_error", {"code": "INVALID_PAYLOAD", "message": "Invalid question data format."}, to=sid)
            return

        user_query = data.get("question")
        # image_hash is the hash of the image currently in focus or most relevant to the query, if any.
        # It can be None if the query is general or refers to images contextually ("the first one").
        current_image_hash_focus = data.get("image_hash") 

        if not user_query:
            await sio.emit("processing_error", {"code": "MISSING_PARAMETER", "message": "Missing 'question' parameter."}, to=sid)
            return
        
        # Optional: Validate current_image_hash_focus if provided
        if current_image_hash_focus:
            session_images = crew.session_store.get_session_images(session_id)
            if not any(img.get('hash') == current_image_hash_focus for img in session_images):
                await handle_session_error(sid, f"Image with hash '{current_image_hash_focus}' not found in this session. Please upload or select a valid image.", "IMAGE_NOT_IN_SESSION", "warning")
                return
        
        crew.session_store.touch_session(session_id) # Refresh session TTL
        
        # Prepare inputs for the crew
        crew_inputs = {
            "session_id": session_id,
            "user_query": user_query,
            # Pass current_image_hash_focus. SessionContextManager will use this.
            "current_image_focus_hash": current_image_hash_focus 
        }
        
        print(f"Processing user question for session {session_id} with inputs: {crew_inputs}")
        
        # Process with CrewAI - run() now takes a single dict of inputs
        # The hierarchical manager in the crew will determine the flow.
        result = crew.run(inputs=crew_inputs)
        
        # Emit the raw result from the crew for now.
        # The client-side will need to parse this (it should be a dict/JSON string).
        # The 'final_answer_text' from ResponseSynthesizer's task is what the user sees.
        print(f"Crew result for session {session_id}: {result}")
        await sio.emit("analysis_result", {
            "question": user_query,
            "result": result # This is the direct output of crew.run()
        }, to=sid)
        
    except Exception as e: # Catch generic exception
        error_message = f"Analysis pipeline failed: {str(e)}"
        print(f"Error in user_question for SID {sid}, session {session_id if 'session_id' in locals() else 'N/A'}: {error_message}")
        import traceback
        traceback.print_exc() # Log full traceback for server-side debugging
        await sio.emit("processing_error", {
            "code": "ANALYSIS_PIPELINE_FAILURE",
            "message": error_message # Send a user-friendly part of the error or a generic message
        }, to=sid)