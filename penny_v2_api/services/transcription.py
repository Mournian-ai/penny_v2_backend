import logging, asyncio, os, tempfile
from faster_whisper import WhisperModel
from penny_v2_api.config import settings
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import TranscriptionRequest, LogEvent

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.model: WhisperModel = None
        self._running = False

    async def start(self):
        """Load the Whisper model and subscribe to transcription events."""
        if self._running:
            return
        # Subscribe to TranscriptionRequest events
        self.event_bus.subscribe_async(TranscriptionRequest, self.handle_transcription_request)
        # Load the Whisper model (could be large, do in background)
        await self._load_model()
        self._running = True

    async def _load_model(self):
        try:
            # Load the model (e.g., tiny, base, or a path to model files)
            self.model = WhisperModel(settings.WHISPER_MODEL_SIZE, 
                                      device=settings.TRANSCRIPTION_DEVICE, 
                                      compute_type=settings.WHISPER_COMPUTE_TYPE)
            await self.event_bus.publish(LogEvent(f"Whisper model '{settings.WHISPER_MODEL_SIZE}' loaded."))
        except Exception as e:
            logger.error(f"Could not load Whisper model: {e}", exc_info=True)

    async def stop(self):
        """Unload the model if needed."""
        self._running = False
        self.model = None

    async def handle_transcription_request(self, event: TranscriptionRequest):
        """Handle incoming audio and produce a transcription."""
        if not self.model:
            event.response_future.set_exception(Exception("Transcription model not loaded"))
            return
        try:
            # Offload heavy transcription to a thread to avoid blocking
            loop = asyncio.get_running_loop()
            def transcribe_audio_bytes(audio_bytes: bytes) -> str:
                # Write bytes to a temp WAV file
                tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                try:
                    tmp_file.write(audio_bytes)
                    tmp_file.flush()
                    tmp_path = tmp_file.name
                finally:
                    tmp_file.close()
                try:
                    segments, _ = self.model.transcribe(tmp_path)
                    # Combine segment texts
                    text = "".join([s.text for s in segments]).strip()
                finally:
                    # Clean up temp file
                    os.remove(tmp_path)
                return text

            result_text = await loop.run_in_executor(None, transcribe_audio_bytes, event.audio_data)
            event.response_future.set_result(result_text)
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            event.response_future.set_exception(e)
