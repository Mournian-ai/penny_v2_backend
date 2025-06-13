import logging
import asyncio
import io
import wave
import disnake
from disnake.ext import commands
from discord.ext import voice_recv
from collections import defaultdict
from penny_v2_api.config import AppConfig
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import (
    PlayAudioInDiscordEvent,
    LogEvent,
    BroadcastTranscriptionEvent,
    TranscriptionRequest,
)

logger = logging.getLogger(__name__)

class AudioSink(voice_recv.AudioSink):
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.user_audio_data = defaultdict(io.BytesIO)

    def write(self, user_id: int, pcm_data: bytes):
        self.user_audio_data[user_id].write(pcm_data)

    def wants_opus(self):
        return False

    def cleanup(self):
        return

class DiscordBotService:
    def __init__(self, event_bus: EventBus, settings: AppConfig):
        self.event_bus = event_bus
        self.settings = settings
        intents = disnake.Intents.default()
        intents.message_content = True
        intents.voice_states = True

        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.voice_client: disnake.VoiceClient = None
        self.sink: AudioSink = None
        self._running = False
        self._task = None

        self._setup_bot_events()
        self.event_bus.subscribe_async(PlayAudioInDiscordEvent, self.handle_play_audio_request)

    def _setup_bot_events(self):
        @self.bot.event
        async def on_ready():
            await self.event_bus.publish(LogEvent(f"Discord Bot logged in as {self.bot.user}"))
            guild = self.bot.get_guild(self.settings.DISCORD_GUILD_ID)
            if guild:
                channel = guild.get_channel(self.settings.DISCORD_VOICE_CHANNEL_ID)
                if isinstance(channel, disnake.VoiceChannel):
                    await self.join_voice_channel(channel)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self.bot.start(self.settings.DISCORD_BOT_TOKEN))

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self.voice_client:
            self.voice_client.stop_listening()
            await self.voice_client.disconnect()
        if self._task:
            self._task.cancel()
        await self.bot.close()

    async def join_voice_channel(self, channel: disnake.VoiceChannel):
        try:
            self.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
            self.sink = AudioSink(self.event_bus)
            self.voice_client.listen(self.sink)
            await self.event_bus.publish(LogEvent(f"Connected to VC: {channel.name} and listening."))
        except Exception as e:
            logger.error(f"Error connecting to voice channel: {e}", exc_info=True)

    async def handle_user_finished_speaking(self, user_id: int, username: str):
        audio_buffer = self.sink.user_audio_data.get(user_id)
        if not audio_buffer or audio_buffer.tell() == 0:
            return

        audio_buffer.seek(0)
        wav_bytes = io.BytesIO()
        with wave.open(wav_bytes, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(audio_buffer.read())

        self.sink.user_audio_data[user_id] = io.BytesIO()

        try:
            wav_bytes.seek(0)
            audio_data = wav_bytes.read()
            future = asyncio.get_event_loop().create_future()
            await self.event_bus.publish(TranscriptionRequest(audio_data=audio_data, response_future=future))
            text = await asyncio.wait_for(future, timeout=60.0)
            if text:
                await self.event_bus.publish(BroadcastTranscriptionEvent(username=username, text=text))
        except Exception as e:
            logger.error(f"Failed to process audio for {username}: {e}", exc_info=True)

    async def handle_play_audio_request(self, event: PlayAudioInDiscordEvent):
        if not self.voice_client or not self.voice_client.is_connected():
            event.response_future.set_exception(Exception("Not connected to a voice channel."))
            return
        try:
            if self.voice_client.is_playing():
                self.voice_client.stop()
            audio_source = io.BytesIO(event.audio_data)
            source = disnake.FFmpegPCMAudio(audio_source, pipe=True)
            self.voice_client.play(source)
            event.response_future.set_result(True)
        except Exception as e:
            event.response_future.set_exception(e)
