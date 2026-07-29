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
    # ⚠️ [2026-07-29 실측] `0.0.0.0` 은 Windows 에서 **IPv4 에만** 바인딩된다. 브라우저는
    #   `http://localhost:8080` 을 `::1`(IPv6)로 **먼저** 해석하므로, 서버가 떠 있는데도
    #   **브라우저에서만 모든 API 가 `Failed to fetch`** 가 된다(서버측 스크립트·카나리는
    #   127.0.0.1 로 붙어 멀쩡하니 원인이 프론트에 있는 것처럼 보인다 — 실제로 그렇게 헤맸다).
    #   ★ 여기를 `::` 로 바꾸면 Windows 에서는 이번엔 **IPv6 전용**이 되어 127.0.0.1 을 쓰는
    #     기존 스크립트·카나리가 전부 깨진다(실측 확인). 그래서 **바인딩은 건드리지 않고**
    #     프론트의 기본 API 주소를 `127.0.0.1` 로 고정해 해결했다(`frontend/src/lib/api.ts`).
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=dev_mode)
