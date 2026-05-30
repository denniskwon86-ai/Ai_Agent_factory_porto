from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 데이터베이스 연결 URL 설정
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy 엔진 생성
# SQLite는 기본적으로 단일 스레드에서만 작동하므로, FastAPI와 같은 멀티스레드 환경에서는
# "check_same_thread": False 옵션을 추가해야 합니다.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 데이터베이스 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 ORM 모델의 기반 클래스
Base = declarative_base()

def get_db():
    """
    의존성 주입을 위한 데이터베이스 세션 제공 함수입니다.
    요청마다 새로운 세션을 생성하고, 요청이 완료되면 세션을 닫습니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()