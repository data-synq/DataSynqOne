from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None)

    paperless_base_url: str = "http://paperless:8000"
    paperless_api_token: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    cors_origins: list[str] = ["http://localhost:8080"]

    database_url: str = "postgresql://brain:brain@vectordb:5432/brain"
    embedding_model: str = "text-embedding-3-small"


settings = Settings()
