import asyncio
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from penny_v2_api.config import AppConfig
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import LogEvent
from penny_v2_api.services.discord_bot import DiscordBotService
from penny_v2_api.services.transcription import TranscriptionService
from penny_v2_api.services.memory import MemoryService
from penny_v2_api.api_server import ApiServer

# Configuration and Event System
settings = AppConfig()
event_bus = EventBus()

# Services
discord_service = DiscordBotService(event_bus, settings)
transcription_service = TranscriptionService(event_bus)
memory_service = MemoryService(event_bus, settings)

# API
api_server = ApiServer(event_bus)
app = api_server.get_app()

# Lifespan replaces deprecated on_event startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await memory_service.start()
        await transcription_service.start()
        await discord_service.start()
        await event_bus.publish(LogEvent("All services started."))
        yield
    finally:
        await discord_service.stop()
        await event_bus.publish(LogEvent("Services shut down."))

# Attach lifespan to app
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
