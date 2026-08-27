import os
import sys

import uvicorn


def _apply_installation_settings() -> None:
    """★★★ [2026-08-24] 이 **설치본**의 값을 적용한다(`data/instance.json`).

    ## 왜 여기인가 — `config.py` 에 넣었다가 시험 100건이 깨졌다

    `config.ECM_DEFAULT_TENANT_ID` 를 import 시점에 파일에서 읽게 했더니, **시험이
    개발자의 `data/` 에 의존**하게 됐다(`TENANT_MISMATCH` 100건). 파일이 있는 기계에서만
    빨강이 되는 상태다.

    ★ `run.py` 는 **앱을 띄우는 사람만** 지나는 길이다. 시험은 `main:app` 을 직접 import
      하므로 이 함수를 밟지 않는다 — 설치본 설정과 시험 격리가 둘 다 성립한다.

    ## 왜 테넌트를 설치본마다 정해야 하는가

    정본 스타터 키트의 CSV 는 **행마다** `tenant_id` 를 담는다(`tenant-afs-demo-materials`).
    색인은 그 행 내용과 인증판의 테넌트가 **같은지 대조**한다 — 다르면 거부한다(옳다).
    그러니 설치본의 기본 테넌트가 자료와 같아야 한다. 열만 바꿔치기하면 그 대조에서 죽는다.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "instance.json")
    try:
        from core.installation_context import apply_file
        result = apply_file(path)
    except Exception as e:  # noqa: BLE001
        # 회사·조직 문맥을 반쪽만 적용한 채 서버를 열면 이름은 맞고 권한 경계는 틀린다.
        # 설치 설정이 존재하는데 적용하지 못한 경우에는 fail-closed 로 기동을 중단한다.
        raise RuntimeError(f"[run] 설치본 문맥을 적용하지 못했습니다: {e}") from e
    if result.get("applied"):
        print(f"[run] 설치본: {result['company_name']} · {result['tenant_id']} · "
              f"조직 노드 {len(result.get('scope_node_ids') or [])}개")


if __name__ == "__main__":
    _apply_installation_settings()
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
    # ★★★ [2026-08-26] 포트를 고를 수 있게 한다 — 기본은 그대로 8080 이다.
    #
    # ⚠️⚠️ 왜 필요한가: 검증용 서버를 `uvicorn main:app` 으로 직접 띄웠더니 **이 파일이
    #   하는 일(`_apply_installation_settings`)을 건너뛰었다.** 그러면 설치본 테넌트가
    #   적용되지 않아, 같은 코드·같은 사용자·같은 프로젝트인데 8080 은 200 이고 검증
    #   서버는 `TENANT_MISMATCH` 404 가 된다(실측). 원인을 코드에서 찾다 한참 헤맸다.
    # ★ 검증 경로가 **제품 경로**여야 한다. 그래서 우회로를 만들지 않고, 제품이 지나는
    #   이 길에 포트 선택만 붙인다.
    port = 8080
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            raise SystemExit("[run] --port 뒤에 포트 번호를 적으십시오. 예: --port 8083")
    if port != 8080:
        print(f"[run] 포트 {port} 로 기동합니다(기본 8080 아님).")
    #: ★★★ [2026-08-27 한시 조치] **어느 모델 모드로 도는지 기동 때 알린다.**
    #:
    #: ⚠️ 게이트웨이는 **지연 초기화**라(`_LazyGateway` — import 때 네트워크를 타지
    #:   않으려는 설계) 그 배너는 첫 LLM 호출에서야 찍히고, 그때는 이미 파이프라인
    #:   로그에 묻힌다. 긴 완주를 시작하기 **전에** 확인할 수 있어야 한다.
    #: ★ 여기서 게이트웨이를 만들지 않는다 — 판정 함수만 부른다(네트워크 없음).
    try:
        from core.llm_gateway import _openrouter_only
        if _openrouter_only():
            import config as _cfg
            print("[run] === OpenRouter 전용 모드 === (한시 조치, AFS_OPENROUTER_ONLY=0 으로 해제)")
            print(f"[run]   Pro   : {' -> '.join(getattr(_cfg, 'OPENROUTER_ONLY_PRO_CHAIN', []))}")
            print(f"[run]   Flash : {' -> '.join(getattr(_cfg, 'OPENROUTER_ONLY_FLASH_CHAIN', []))}")
    except Exception as _e:                       # 알림 실패가 기동을 막지 않는다
        print(f"[run] (모델 모드 확인 실패, 기동은 계속: {_e})")

    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev_mode)
