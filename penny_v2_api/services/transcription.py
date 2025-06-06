# ==============================================================================
# penny_v2_api/services/transcription.py
# (No changes needed)
# ==============================================================================
import logging
import asyncio
from faster_whisper import WhisperModel
from penny_v2_api.config import settings
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import TranscriptionRequest, LogEvent

logger_transcription = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus; self.model = None; self._running = False
    async def start(self):
        if self._running: return
        self.event_bus.subscribe_async(TranscriptionRequest, self.handle_transcription_request)
        await self._load_model(); self._running = True
    async def stop(self): self._running = False; self.model = None
    async def _load_model(self):
        try:
            self.model = WhisperModel(settings.WHISPER_MODEL_SIZE, device=settings.TRANSCRIPTION_DEVICE, compute_type=settings.WHISPER_COMPUTE_TYPE)
            await self.event_bus.publish(LogEvent(f"Whisper model '{settings.WHISPER_MODEL_SIZE}' loaded."))
        except Exception as e: logger_transcription.error(f"Fatal: Could not load Whisper model. {e}", exc_info=True)
    async def handle_transcription_request(self, event: TranscriptionRequest):
        if not self.model: event.response_future.set_exception(Exception("Transcription model not available.")); return
        try:
            segments, _ = await asyncio.get_running_loop().run_in_executor(None, self.model.transcribe, event.audio_data)
            result_text = "".join([s.text for s in segments]).strip()
            event.response_future.set_result(result_text)
        except Exception as e: event.response_future.set_exception(e)