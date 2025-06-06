# ==============================================================================
# penny_v2_api/services/discord_bot.py
# CORRECTED to use the modern disnake voice recording API.
# ==============================================================================
import logging
import asyncio
import disnake
import io
import wave

from disnake.ext import commands
from collections import defaultdict 

from penny_v2_api.config import settings
from penny_v2_api.core.event_bus import EventBus
from penny_v2_api.core.events import PlayAudioInDiscordEvent, LogEvent, BroadcastTranscriptionEvent, TranscriptionRequest

logger_discord = logging.getLogger(__name__)

class AudioSink(disnake.reader.AudioSink):
    """Custom AudioSink to handle raw audio data from users."""
    def __init__(self, event_bus, voice_client):
        self.event_bus = event_bus
        self.voice_client = voice_client
        self.user_audio_data = defaultdict(io.BytesIO)

    def write(self, data, user):
        if user is None: return
        self.user_audio_data[user.id].write(data.pcm)

    async def on_user_speaking_end(self, user):
        """Called when a user stops speaking."""
        if user.bot: return
        
        audio_buffer = self.user_audio_data.get(user.id)
        if not audio_buffer or audio_buffer.tell() == 0:
            return # No audio recorded for this user

        # Convert raw PCM to a proper WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.voice_client.decoder.CHANNELS)
            wf.setsampwidth(self.voice_client.decoder.SAMPLE_SIZE // self.voice_client.decoder.CHANNELS)
            wf.setframerate(self.voice_client.decoder.SAMPLING_RATE)
            audio_buffer.seek(0)
            wf.writeframes(audio_buffer.read())
        
        # Reset the buffer for the next time this user speaks
        self.user_audio_data[user.id] = io.BytesIO()

        try:
            # Send the complete WAV data for transcription
            wav_buffer.seek(0)
            future = asyncio.Future()
            await self.event_bus.publish(TranscriptionRequest(audio_data=wav_buffer.read(), response_future=future))
            text = await asyncio.wait_for(future, timeout=120)
            if text:
                await self.event_bus.publish(BroadcastTranscriptionEvent(username=user.display_name, text=text))
        except Exception as e:
            logger_discord.error(f"Audio processing failed for {user.display_name}: {e}")

class DiscordBotService:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        intents = disnake.Intents.default()
        intents.voice_states = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self._running = False; self._task = None; self.voice_client = None

    async def start(self):
        if self._running or not settings.DISCORD_BOT_TOKEN: return
        self._running = True
        self.event_bus.subscribe_async(PlayAudioInDiscordEvent, self.handle_play_audio_request)
        self.setup_bot_events()
        self._task = asyncio.create_task(self.bot.start(settings.DISCORD_BOT_TOKEN))

    async def stop(self):
        if not self._running: return
        self._running = False
        if self._task: self._task.cancel()
        await self.bot.close()

    def setup_bot_events(self):
        @self.bot.event
        async def on_ready():
            await self.event_bus.publish(LogEvent(f'Discord Bot logged in as {self.bot.user}'))
            guild = self.bot.get_guild(settings.DISCORD_GUILD_ID)
            if guild:
                channel = guild.get_channel(settings.DISCORD_VOICE_CHANNEL_ID)
                if isinstance(channel, disnake.VoiceChannel): await self.join_voice_channel(channel)

    async def join_voice_channel(self, channel: disnake.VoiceChannel):
        try:
            self.voice_client = await channel.connect(cls=disnake.reader.VoiceReader)
            # Create a sink and pass it the event bus and voice client
            sink = AudioSink(self.event_bus, self.voice_client)
            # Start recording with the custom sink
            self.voice_client.listen(sink)
            await self.event_bus.publish(LogEvent(f'Connected to VC: {channel.name} and listening.'))
        except Exception as e: logger_discord.error(f"Error connecting to VC: {e}", exc_info=True)

    async def handle_play_audio_request(self, event: PlayAudioInDiscordEvent):
        if not self.voice_client or not self.voice_client.is_connected():
            event.response_future.set_exception(Exception("Not connected to voice channel.")); return
        try:
            if self.voice_client.is_playing(): self.voice_client.stop()
            audio_source = io.BytesIO(event.audio_data)
            source = disnake.FFmpegPCMAudio(audio_source, pipe=True)
            self.voice_client.play(source)
            event.response_future.set_result(True)
        except Exception as e: event.response_future.set_exception(e)