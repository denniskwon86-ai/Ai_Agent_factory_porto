from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    """
    환경 변수를 관리하는 설정 클래스입니다.
    .env 파일에서 환경 변수를 로드합니다.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    NODE_ENV: str = "development"
    PORT: int = 8000
    DATABASE_URL: str = "sqlite:///./sql_app.db" # SQLite 데이터베이스 URL

settings = Settings()