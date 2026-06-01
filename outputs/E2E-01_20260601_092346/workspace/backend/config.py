from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://user:password@db:5432/mydatabase"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()