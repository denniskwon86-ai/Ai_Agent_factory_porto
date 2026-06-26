import sys
import uvicorn

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    # main.py의 app 객체를 8000 포트에서 실행합니다.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)