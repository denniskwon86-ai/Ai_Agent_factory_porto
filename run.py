import sys
import uvicorn

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    # main.py의 app 객체를 8080 포트에서 실행합니다.
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)