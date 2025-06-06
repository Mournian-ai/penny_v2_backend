# ==============================================================================
# penny_v2_api/main.py
# ==============================================================================
import asyncio
import logging
import sys
import uvicorn
from penny_v2_api.config import settings
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.services.transcription import TranscriptionService
from penny_v2_api.services.music import MusicGenerationService
from penny_v2_api.services.discord_bot import DiscordBotService
from penny_v2_api.api_server import ApiServer

logging.basicConfig(level=settings.LOG_LEVEL.upper(), format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger_main = logging.getLogger(__name__)

class UnifiedApiApp:
    def __init__(self):
        self.event_bus = EventBus()
        self.transcription_service = TranscriptionService(self.event_bus)
        self.music_service = MusicGenerationService(self.event_bus)
        self.discord_bot_service = DiscordBotService(self.event_bus)
        self.api_server = ApiServer(self.event_bus)
        self.services = [self.transcription_service, self.music_service, self.discord_bot_service]

    async def start_all(self):
        logger_main.info("Starting all services...")
        await asyncio.gather(*(s.start() for s in self.services))
        logger_main.info("All services started.")

    async def stop_all(self):
        logger_main.info("Stopping all services...")
        await asyncio.gather(*(s.stop() for s in reversed(self.services)))

def create_app():
    app_instance = UnifiedApiApp()
    fastapi_app = app_instance.api_server.get_app()
    @fastapi_app.on_event("startup")
    async def startup(): asyncio.create_task(app_instance.start_all())
    @fastapi_app.on_event("shutdown")
    async def shutdown(): await app_instance.stop_all()
    return fastapi_app

app = create_app()

# To run: uvicorn penny_v2_api.main:app --host 0.0.0.0 --port 8000