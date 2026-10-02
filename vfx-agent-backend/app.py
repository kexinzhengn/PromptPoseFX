"""PromptPoseFX FastAPI application."""

import json
import os
import threading
import time
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional

from agent.agent import process_user_message
from agent.schemas import EffectMention
from chat_manager import ChatManager
from config import CORS_ORIGINS, SERVER_HOST, SERVER_PORT
from editor_controls import EditorSelection, EditorState
from effect_repository import (
    EffectEditorRevisionError,
    EffectEditorStateError,
    EffectNotFoundError,
    EffectParameterError,
)
from run_manager import RunManager, RunBusyError

from video_process.pipeline import start_processing, get_status
from video_process.video_processor import video_to_frames

app = FastAPI(title="PromptPoseFX API")

# The development frontend is the only allowed cross-origin caller by default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_chat_manager = ChatManager()
_run_manager = RunManager()


# Request and response models.

class OptionItem(BaseModel):
    id: str
    label: str
    description: str


class ChatRequest(BaseModel):
    video_id: str
    user_input: str
    thread_id: str = ""
    effect_id: str = ""
    effect_messages: list[dict] = Field(default_factory=list)
    prev_code: str = ""
    effect_name: str = ""
    effect_list: list[dict] = Field(default_factory=list)
    pinned_joints: dict[str, str] = Field(default_factory=dict)
    effect_mentions: list[EffectMention] = Field(default_factory=list)
    selected_option_id: str | None = None
    editor_revision: int | None = Field(default=None, ge=0)
    editor_selection: EditorSelection | None = None


class ChatResponse(BaseModel):
    thread_id: str
    response: str
    options: list[OptionItem] | None = None
    options_header: str | None = None
    effect_messages: list[dict]
    new_effect: Optional[dict] = None
    effect_update: Optional[dict] = None


class ParameterRangeUpdate(BaseModel):
    min: float
    max: float

    @field_validator("min", "max", mode="before")
    @classmethod
    def reject_boolean_bounds(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Slider range bounds must be numbers")
        return value


class EffectPatchRequest(BaseModel):
    name: str | None = None
    parameter_updates: dict[str, Any] = Field(default_factory=dict)
    parameter_range_updates: dict[str, ParameterRangeUpdate] = Field(default_factory=dict)


class WorkspaceCreateRequest(BaseModel):
    effect_id: str = Field(min_length=1, max_length=128)
    video_id: str = Field(min_length=1, max_length=128)


class EditorStateReplaceRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    editor_state: EditorState


# Routes.

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Process one synchronous chat turn."""
    try:
        result = process_user_message(
            video_id=request.video_id,
            user_input=request.user_input,
            thread_id=request.thread_id or request.effect_id,
            effect_id=request.effect_id,
            effect_messages=request.effect_messages,
            prev_code=request.prev_code,
            effect_name=request.effect_name,
            effect_list=request.effect_list,
            pinned_joints=request.pinned_joints,
            effect_mentions=[mention.model_dump() for mention in request.effect_mentions],
            selected_option_id=request.selected_option_id,
        )
        return ChatResponse(
            thread_id=result.get("thread_id", ""),
            response=result["response"],
            options=result.get("options"),
            options_header=result.get("options_header"),
            effect_messages=result["effect_messages"],
            new_effect=result.get("new_effect"),
            effect_update=result.get("effect_update"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """Stream one chat turn over Server-Sent Events."""
    def event_stream():
        events = []
        lock = threading.Lock()
        done = threading.Event()
        result = {}
        error = None

        def progress(stage, content):
            with lock:
                events.append({"type": "stage", "stage": stage, "content": content})

        def run():
            nonlocal result, error
            try:
                result = process_user_message(
                    video_id=request.video_id,
                    user_input=request.user_input,
                    thread_id=request.thread_id or request.effect_id,
                    effect_id=request.effect_id,
                    effect_messages=request.effect_messages,
                    prev_code=request.prev_code,
                    effect_name=request.effect_name,
                    effect_list=request.effect_list,
                    pinned_joints=request.pinned_joints,
                    effect_mentions=[mention.model_dump() for mention in request.effect_mentions],
                    selected_option_id=request.selected_option_id,
                    progress_callback=progress,
                )
            except Exception as e:
                error = str(e)
            finally:
                done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()

        last_count = 0
        while not done.is_set() or last_count < len(events):
            while last_count < len(events):
                with lock:
                    evt = events[last_count]
                    last_count += 1
                yield f"event: stage\ndata: {json.dumps({'stage': evt['stage'], 'content': evt['content']})}\n\n"

            if done.is_set():
                break

            time.sleep(0.1)

        if error:
            yield f"event: error\ndata: {json.dumps({'detail': error})}\n\n"
        else:
            chat_response = {
                "thread_id": result.get("thread_id", ""),
                "response": result["response"],
                "options": result.get("options"),
                "options_header": result.get("options_header"),
                "effect_messages": result["effect_messages"],
                "new_effect": result.get("new_effect"),
                "effect_update": result.get("effect_update"),
            }
            yield f"event: complete\ndata: {json.dumps(chat_response)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chat/run")
def chat_run(request: ChatRequest):
    """Submit a background chat run and return its stable identifiers."""
    thread_id = request.thread_id or request.effect_id or uuid.uuid4().hex
    try:
        editor_context = None
        if request.editor_revision is not None:
            if request.editor_selection is None:
                raise EffectEditorStateError(
                    "editor_selection is required with editor_revision"
                )
            editor_context = _chat_manager.get_editor_context_snapshot(
                effect_id=thread_id,
                video_id=request.video_id,
                expected_revision=request.editor_revision,
                selection=request.editor_selection,
            )
        run_id = _run_manager.start(
            thread_id=thread_id,
            video_id=request.video_id,
            user_input=request.user_input,
            pinned_joints=request.pinned_joints or {},
            effect_mentions=[mention.model_dump() for mention in request.effect_mentions],
            selected_option_id=request.selected_option_id,
            editor_context=editor_context,
        )
    except RunBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except EffectEditorRevisionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except EffectNotFoundError:
        raise HTTPException(status_code=404, detail="Effect Workspace does not exist") from None
    except EffectEditorStateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return {"run_id": run_id, "thread_id": thread_id}


@app.get("/api/run/{run_id}/events")
def run_events(run_id: str):
    """Replay and stream run events until a terminal event is emitted."""
    if _run_manager.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run does not exist")
    return StreamingResponse(_run_manager.event_stream(run_id), media_type="text/event-stream")


@app.post("/api/run/{run_id}/cancel")
def cancel_run(run_id: str):
    """Cancel a running task."""
    run = _run_manager.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run does not exist")
    if run["status"] != "running":
        raise HTTPException(status_code=409, detail="Run is not active")
    _run_manager.cancel(run_id)
    return {"run_id": run_id, "status": "cancelled"}


@app.get("/api/effects")
def list_effects():
    """Return all Effect summaries."""
    return {"effects": _chat_manager.get_effect_list()}


@app.post("/api/effects")
def create_workspace(request: WorkspaceCreateRequest):
    """Create or return a pending Effect Workspace bound to one video."""
    total_frames = _read_video_total_frames(request.video_id)
    try:
        detail = _chat_manager.create_workspace(
            request.effect_id,
            request.video_id,
            total_frames,
        )
    except EffectEditorStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    detail["conversation"] = _chat_manager.get_conversation(request.effect_id)
    return detail


@app.get("/api/effect/{effect_id}")
def get_effect(effect_id: str):
    """Return one complete Effect snapshot."""
    detail = _chat_manager.get_effect_detail(effect_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Effect does not exist")
    return detail


@app.patch("/api/effect/{effect_id}")
def patch_effect(effect_id: str, request: EffectPatchRequest):
    """Update an Effect name or current parameters without invoking an Agent."""
    if (
        request.name is None
        and not request.parameter_updates
        and not request.parameter_range_updates
    ):
        raise HTTPException(status_code=422, detail="No Effect updates were provided")
    try:
        detail = _chat_manager.patch_effect(
            effect_id,
            effect_name=request.name,
            parameter_updates=request.parameter_updates,
            parameter_range_updates={
                key: bounds.model_dump()
                for key, bounds in request.parameter_range_updates.items()
            },
        )
    except EffectNotFoundError:
        raise HTTPException(status_code=404, detail="Effect does not exist") from None
    except EffectParameterError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return {
        "effect_update": {
            "effect_id": effect_id,
            "name": detail["name"],
            "params": detail["params"],
            "parameter_ranges": detail["parameter_ranges"],
            "status": detail["status"],
        }
    }


@app.put("/api/effect/{effect_id}/editor-state")
def replace_editor_state(effect_id: str, request: EditorStateReplaceRequest):
    """Replace editor controls using a server-owned revision counter."""
    try:
        detail = _chat_manager.replace_editor_state(
            effect_id,
            request.expected_revision,
            request.editor_state,
        )
    except EffectNotFoundError:
        raise HTTPException(status_code=404, detail="Effect Workspace does not exist") from None
    except EffectEditorRevisionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except EffectEditorStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return {
        "effect_id": effect_id,
        "editor_revision": detail["editor_revision"],
        "editor_state": detail["editor_state"],
    }


@app.delete("/api/effect/{effect_id}")
def delete_effect(effect_id: str):
    """Delete an Effect and its persisted workspace data."""
    if not _chat_manager.delete_effect(effect_id):
        raise HTTPException(status_code=404, detail="Effect does not exist")
    return {"deleted": True}


@app.get("/api/thread/{thread_id}/conversation")
def thread_conversation(thread_id: str):
    """Return conversation history even when generation has failed."""
    return {"conversation": _chat_manager.get_conversation(thread_id)}


# Video upload and processing.

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _read_video_total_frames(video_id: str) -> int:
    """Read the processed frame count from server-owned video metadata."""
    metadata_path = os.path.join(DATA_DIR, video_id, "metadata.json")
    try:
        with open(metadata_path, encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        total_frames = metadata["totalFrames"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=404, detail="Video metadata does not exist") from None
    if not isinstance(total_frames, int) or isinstance(total_frames, bool) or total_frames < 1:
        raise HTTPException(status_code=422, detail="Video metadata has an invalid frame count")
    return total_frames


@app.post("/api/upload")
def upload_video(file: UploadFile = File(...)):
    """Save a video, extract frames, and start pose processing."""
    video_id = uuid.uuid4().hex[:12]
    vid_dir = os.path.join(DATA_DIR, video_id)
    img_dir = os.path.join(vid_dir, "img")
    os.makedirs(img_dir, exist_ok=True)

    # Save uploaded video
    video_path = os.path.join(vid_dir, "video.mp4")
    try:
        content = file.file.read()
        with open(video_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save video: {e}")

    # Extract frames
    try:
        nframe_count = video_to_frames(video_path, img_dir, fps=30, speed=1.0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract frames: {e}")

    # Save metadata
    meta = {
        "id": video_id,
        "totalFrames": nframe_count,
        "fps": 30,
        "width": 640,
        "height": 360,
        "status": "processing",
        "created_at": datetime.now().isoformat(),
    }
    with open(os.path.join(vid_dir, "metadata.json"), "w") as f:
        json.dump(meta, f)

    # Start pose pipeline in background
    start_processing(video_id)

    return meta


@app.get("/api/videos")
def list_videos():
    """Return all locally processed videos."""
    videos = []
    for name in os.listdir(DATA_DIR):
        vid_dir = os.path.join(DATA_DIR, name)
        meta_path = os.path.join(vid_dir, "metadata.json")
        if os.path.isdir(vid_dir) and os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            # Check if processing completed
            has_pose = os.path.exists(os.path.join(vid_dir, "smoothed_landmark.json"))
            meta["status"] = "complete" if has_pose else meta.get("status", "unknown")
            videos.append(meta)
        elif os.path.isdir(vid_dir) and os.path.isdir(os.path.join(vid_dir, "img")):
            # Legacy — no metadata.json, infer from files
            img_count = len([f for f in os.listdir(os.path.join(vid_dir, "img")) if f.endswith((".jpg", ".png"))])
            has_pose = os.path.exists(os.path.join(vid_dir, "smoothed_landmark.json"))
            videos.append({
                "id": name,
                "totalFrames": img_count,
                "fps": 30,
                "width": 640,
                "height": 360,
                "status": "complete" if has_pose else "unknown",
                "created_at": "",
            })
    videos.sort(key=lambda v: v["created_at"], reverse=True)
    return {"videos": videos}


@app.get("/api/process/{video_id}/status")
def process_status(video_id: str):
    """Return pose-processing progress for one video."""
    status = get_status(video_id)
    if not status:
        raise HTTPException(status_code=404, detail="video_id not found")
    return status


# Processed video frames.
app.mount("/api/video", StaticFiles(directory=DATA_DIR), name="video")


# Local development entry point.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
