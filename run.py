import sys
import uvicorn

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    # 기본은 '운영 모드'(reload OFF) - reload 는 리포의 아무 .py 나 저장돼도 서버를 재시작해
    # 실행 중인 스프린트 스트림을 죽인다(완주 스프린트에서 실측된 사고). 코드 수정 작업 중에만
    # `python run.py --dev` 로 자동 리로드를 켠다.
    dev_mode = "--dev" in sys.argv
    if dev_mode:
        print("[run] 개발 모드(reload ON): .py 저장 시 서버가 재시작되어 실행 중 스프린트가 중단됩니다.")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=dev_mode)
