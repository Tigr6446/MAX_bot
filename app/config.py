from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_bot_token: str
    webhook_secret: str = "change_me"
    public_url: str = "http://localhost:8000"
    database_url: str
    my_user_id: int

    @property
    def async_database_url(self) -> str:
        """Приводит DATABASE_URL к формату, понятному SQLAlchemy+asyncpg."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()