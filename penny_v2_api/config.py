from pydantic_settings import BaseSettings, SettingsConfigDict

class UnifiedApiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    TRANSCRIPTION_DEVICE: str = "cuda"
    MUSIC_GEN_DEVICE: str = "cuda"
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_COMPUTE_TYPE: str = "int8"
    MUSIC_MODEL_SIZE: str = "facebook/musicgen-small"
    DISCORD_BOT_TOKEN: str
    DISCORD_GUILD_ID: int
    DISCORD_VOICE_CHANNEL_ID: int

settings = UnifiedApiConfig()