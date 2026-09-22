from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    APP_ENV: str = "development"
    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000,https://shopflow.cryvex.com"
    LOG_LEVEL: str = "INFO"

    @property
    def get_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()