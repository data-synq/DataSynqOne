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

    # Session cookie. `secure` must be false for `make dev`, which serves the app
    # over plain http://localhost — a Secure cookie would never be stored there.
    session_cookie_name: str = "dsq_session"
    session_cookie_secure: bool = True
    session_ttl_hours: int = 12

    # Bootstrap admin, applied only while the users table is still empty. Without
    # both values set, no account is created — there is no default password.
    admin_email: str = ""
    admin_password: str = ""


settings = Settings()
