# ==============================================================================
# penny_v2_api/services/music.py
# (No changes needed)
# ==============================================================================
import logging
import asyncio
import torch
from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write
from penny_v2_api.config import settings
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import MusicGenerationRequest, LogEvent

logger_music = logging.getLogger(__name__)

class MusicGenerationService:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus; self.model = None; self._running = False
    async def start(self):
        if self._running: return
        self.event_bus.subscribe_async(MusicGenerationRequest, self.handle_music_request)
        await self._load_model(); self._running = True
    async def stop(self): self._running = False; self.model = None
    async def _load_model(self):
        try:
            self.model = MusicGen.get_pretrained(settings.MUSIC_MODEL_SIZE, device=settings.MUSIC_GEN_DEVICE)
            await self.event_bus.publish(LogEvent(f"MusicGen model '{settings.MUSIC_MODEL_SIZE}' loaded."))
        except Exception as e: logger_music.error(f"Fatal: Could not load MusicGen model. {e}", exc_info=True)
    async def handle_music_request(self, event: MusicGenerationRequest):
        if not self.model: event.response_future.set_exception(Exception("MusicGen model not available.")); return
        try:
            self.model.set_generation_params(duration=event.duration)
            wav = await asyncio.get_running_loop().run_in_executor(None, self.model.generate, [event.prompt])
            file_path = f"temp_music_{torch.randint(10000, (1,)).item()}.wav"
            audio_write(file_path, wav.cpu().squeeze(0), self.model.sample_rate, strategy="loudness", loudness_compressor=True)
            event.response_future.set_result(file_path)
        except Exception as e: event.response_future.set_exception(e)