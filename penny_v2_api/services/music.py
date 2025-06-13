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
        self.event_bus = event_bus
        self.model = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self.event_bus.subscribe_async(MusicGenerationRequest, self.handle_music_request)
        await self._load_model()
        self._running = True

    async def stop(self):
        self._running = False
        self.model = None

    async def _load_model(self):
        try:
            self.model = MusicGen.get_pretrained(settings.MUSIC_MODEL_SIZE)
            self.model.set_generation_params(duration=30)

            if settings.MUSIC_GEN_DEVICE == "cuda" and torch.cuda.is_available():
                logger_music.info(f"Moving MusicGen model to CUDA with float16 on {torch.cuda.get_device_name(0)}")
                self.model.lm = self.model.lm.cuda().half()
                self.model.compression_model = self.model.compression_model.cuda().half()
            else:
                logger_music.warning("CUDA not available or disabled — using CPU (will be slow).")

            await self.event_bus.publish(LogEvent(f"MusicGen model '{settings.MUSIC_MODEL_SIZE}' loaded."))
        except Exception as e:
            logger_music.error(f"Fatal: Could not load MusicGen model. {e}", exc_info=True)

    async def handle_music_request(self, event: MusicGenerationRequest):
        if not self.model:
            event.response_future.set_exception(Exception("MusicGen model not available."))
            return
        try:
            self.model.set_generation_params(duration=event.duration)

            # Use executor to run sync model generation without blocking event loop
            loop = asyncio.get_running_loop()
            wav = await loop.run_in_executor(None, self.model.generate, [event.prompt])

            file_path = f"temp_music_{torch.randint(10000, (1,)).item()}.wav"
            audio_write(
                file_path,
                wav.cpu().squeeze(0),
                self.model.sample_rate,
                strategy="loudness",
                loudness_compressor=True
            )

            event.response_future.set_result(file_path)
        except Exception as e:
            event.response_future.set_exception(e)
