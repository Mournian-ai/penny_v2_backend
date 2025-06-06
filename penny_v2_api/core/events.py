# ==============================================================================
# penny_v2_api/core/events.py
# ==============================================================================
from dataclasses import dataclass
import asyncio

@dataclass
class BaseEvent: pass
@dataclass
class AppShutdownEvent(BaseEvent): pass
@dataclass
class LogEvent(BaseEvent): message: str; level: str = "INFO"
@dataclass
class TranscriptionRequest(BaseEvent): audio_data: bytes; response_future: asyncio.Future
@dataclass
class MusicGenerationRequest(BaseEvent): prompt: str; duration: int; response_future: asyncio.Future
@dataclass
class PlayAudioInDiscordEvent(BaseEvent): audio_data: bytes; response_future: asyncio.Future
@dataclass
class BroadcastTranscriptionEvent(BaseEvent): username: str; text: str