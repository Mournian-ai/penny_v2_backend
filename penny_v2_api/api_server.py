# ==============================================================================
# penny_v2_api/api_server.py
# REWRITTEN to support the new WebSocket and Audio Playback architecture
# ==============================================================================
import logging
import asyncio
import json
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import TranscriptionRequest, MusicGenerationRequest, PlayAudioInDiscordEvent, BroadcastTranscriptionEvent

logger_api = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self): self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket): await websocket.accept(); self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket): self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections: await connection.send_text(message)

class MusicRequest(BaseModel): prompt: str; duration: int = 30

class ApiServer:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.fastapi_app = FastAPI()
        self.ws_manager = ConnectionManager()
        self._setup_routes()
        self.event_bus.subscribe_async(BroadcastTranscriptionEvent, self.handle_broadcast_transcription)

    async def handle_broadcast_transcription(self, event: BroadcastTranscriptionEvent):
        payload = json.dumps({"type": "transcription", "username": event.username, "text": event.text})
        await self.ws_manager.broadcast(payload)

    def _setup_routes(self):
        self.fastapi_app.post("/transcribe/", self.transcribe_audio)
        self.fastapi_app.post("/generate_music/", self.generate_music)
        self.fastapi_app.post("/play_in_discord/", self.play_in_discord)
        self.fastapi_app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.ws_manager.connect(websocket)
            try:
                while True: await websocket.receive_text()
            except WebSocketDisconnect: self.ws_manager.disconnect(websocket)

    async def transcribe_audio(self, file: UploadFile = File(...)):
        if not file.content_type.startswith('audio/'): raise HTTPException(status_code=400, detail="Invalid audio file.")
        future = asyncio.Future()
        await self.event_bus.publish(TranscriptionRequest(audio_data=await file.read(), response_future=future))
        return JSONResponse(content={"transcription": await future})

    async def generate_music(self, request: MusicRequest):
        future = asyncio.Future()
        await self.event_bus.publish(MusicGenerationRequest(prompt=request.prompt, duration=request.duration, response_future=future))
        return FileResponse(path=await future, media_type='audio/wav', filename='generated_music.wav')

    async def play_in_discord(self, file: UploadFile = File(...)):
        if not file.content_type.startswith('audio/'): raise HTTPException(status_code=400, detail="Invalid audio file.")
        future = asyncio.Future()
        await self.event_bus.publish(PlayAudioInDiscordEvent(audio_data=await file.read(), response_future=future))
        await future
        return JSONResponse(content={"status": "audio_playback_initiated"})
    
    def get_app(self): return self.fastapi_app