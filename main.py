import os
import sys

# uvicorn reload=True 워커 자식 프로세스는 run.py의 stdout 재설정을 상속받지 못한다.
# 워커가 import하는 진입점(main.py)에서 직접 UTF-8로 고정하여 cp949 콘솔에서의
# 이모지 print UnicodeEncodeError(파이프라인 500 크래시)를 영구 방지한다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.sys_logger import StdoutInterceptor
sys.stdout = StdoutInterceptor(sys.stdout)
sys.stderr = StdoutInterceptor(sys.stderr)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import factory_control, realtime, format_control

# 슈퍼바이저 데몬 초기화 (백그라운드 이벤트 리스너 등록)
import core.supervisor_daemon

app = FastAPI(
    title="V5.0 AI Factory Studio API",
    description="범용 자율형 소프트웨어 팩토리 플랫폼 관제용 비동기 API",
    version="5.1.0"
)

# [QA 보완] 하드코딩 배제: 운영 서버와 로컬 환경을 분리하기 위해 환경 변수 사용
allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(factory_control.router)
app.include_router(format_control.router)
app.include_router(realtime.router)