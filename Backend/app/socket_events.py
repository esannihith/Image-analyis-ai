import socketio
from .crew import ImageMetadataConversationalAssistantCrew
from .store.session_store import SessionStore
import uuid
import json
import os

crew = ImageMetadataConversationalAssistantCrew()
session_store = SessionStore()

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', engineio_logger=True)

@sio.event
async def connect(sid, environ):
    print(f"Socket connected: {sid}")
    # Wait for frontend to send session_id via session_init

@sio.event
async def disconnect(sid):
    print(f"Socket disconnected: {sid}")

@sio.event
async def session_init(sid, data):
    # Frontend sends session_id (or empty for new session)
    session_id = data.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    await sio.save_session(sid, {'session_id': session_id})
    await sio.enter_room(sid, session_id)
    session_store.set_metadata(session_id, "__session__", {"created_at": str(uuid.uuid1())})
    await sio.emit("session", {"success": True, "sid": sid, "session_id": session_id}, to=sid)

@sio.event
async def user_question(sid, data):
    session_id = data.get("session_id")
    image_id = data.get("image_id")
    question = data.get("question")
    if not (session_id and image_id and question):
        await sio.emit("answer", {"success": False, "error": "Missing session_id, image_id, or question."}, to=sid)
        return
    session_store.touch_session(session_id)
    try:
        # Use CrewAI's built-in orchestration via the OrchestrationManager and tasks.yaml
        result = crew.run_task(
            "assemble_response",
            session_id=session_id,
            image_id=image_id,
            user_question=question
        )
        import json
        answer_data = result if isinstance(result, dict) else json.loads(result)
        if not answer_data.get("success"):
            await sio.emit("answer", {"success": False, "error": answer_data.get("error", "CrewAI answer failed.")}, to=sid)
            return
        await sio.emit("answer", {
            "success": True,
            "answer": answer_data.get("final_response"),
            "image_id": image_id,
            "session_id": session_id
        }, to=sid)
    except Exception as e:
        await sio.emit("answer", {"success": False, "error": f"CrewAI pipeline error: {str(e)}"}, to=sid)
