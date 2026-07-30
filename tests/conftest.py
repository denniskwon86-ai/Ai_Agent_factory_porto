"""테스트 전역 격리 — **테스트가 실제 운영 로그를 오염시키지 않게 한다.**

## 왜 필요한가 (2026-07-29 실측)

`data/quality_outcomes.jsonl` 에 프로젝트명이 빈 실패 기록 4건이 쌓여 있었다. 카나리가 남긴
것이 아니라 **pytest 가 남긴 것**이었다 — 게이트 계측이 `nodes/utils/scoring.py` 에 붙어
있으므로, 채점기를 부르는 어떤 테스트든 실로그에 한 줄을 쓴다.

⚠️ 이건 단순한 지저분함이 아니다. 그 로그는 **품질 지표의 원천**이고, 카나리 증적으로 제출된다.
  테스트가 만든 가짜 실패가 섞이면 "게이트 실패율"이 오염되고, 그 숫자로 모델·프롬프트를
  판단하게 된다. 계측의 신뢰성은 "무엇이 들어오는가"만큼 **"무엇이 들어오지 않는가"** 에 달렸다.

개별 테스트가 자기 것을 monkeypatch 하는 것으로는 부족하다 — 계측을 의식하지 않는 테스트가
문제이기 때문이다. 그래서 **전역 autouse** 로 막는다.
"""
import shutil

import pytest


@pytest.fixture(scope="session")
def _master_db_template(tmp_path_factory):
    """빈 기준정보 스키마를 **세션당 한 번** 만든다.

    ★ 테스트마다 `_init_db()`(DDL 40여 개 + 컬럼 마이그레이션)를 돌리면 전체 실행이 88초 →
      173초로 늘어난다(실측). 스키마는 어차피 같으므로 한 번 만들고 파일을 복사한다.
      느린 격리는 결국 꺼지고, 꺼진 격리는 없는 것과 같다."""
    p = tmp_path_factory.mktemp("master_tpl") / "master.db"
    from core.master_data import MasterData
    MasterData(db_path=str(p))          # DDL·마이그레이션 1회
    # WAL 잔여를 본체로 합친다 — 복사본만 들고 가면 -wal 에 남은 스키마가 유실된다.
    import sqlite3
    conn = sqlite3.connect(str(p))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return str(p)


@pytest.fixture(autouse=True)
def _isolate_runtime_telemetry(tmp_path, monkeypatch, _master_db_template):
    """모든 테스트의 텔레메트리 기록을 tmp 로 돌린다(개별 테스트가 다시 덮어써도 무해)."""
    try:
        from core import quality_telemetry
        monkeypatch.setattr(quality_telemetry, "_LOG_PATH",
                            str(tmp_path / "quality_outcomes.jsonl"), raising=False)
    except Exception:
        pass
    try:
        import core.llm_gateway as gw
        monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH",
                            str(tmp_path / "llm_call_log.jsonl"), raising=False)
    except Exception:
        pass
    try:
        # 감사로그는 특히 중요하다 — 테스트가 남긴 거부 기록이 섞이면 "실제 침해 시도"를
        # 세는 지표가 오염되고, 반대로 테스트는 남의 기록을 보고 통과할 수 있다(실제 발생).
        from core.enterprise_context import audit
        monkeypatch.setattr(audit, "_LOG_PATH",
                            str(tmp_path / "access_audit.jsonl"), raising=False)
    except Exception:
        pass
    try:
        # 승격 기록도 같은 이유로 격리한다 — 테스트가 남긴 전사 승격이 실제 목록에 섞이면
        # "이 앱이 전사 앱인가"의 답이 틀린다.
        from core import workspace_promotion
        monkeypatch.setattr(workspace_promotion.workspace, "db_path",
                            str(tmp_path / "workspace.db"), raising=False)
        # 운영 준비(체크리스트·롤백)도 같은 저장소를 쓴다 — 롤백 기록이 실제 이력에 섞이면
        #   "이 릴리스가 내려간 적이 있나"의 답이 틀린다.
        from core import release_readiness
        monkeypatch.setattr(release_readiness.release_readiness, "db_path",
                            str(tmp_path / "workspace.db"), raising=False)
    except Exception:
        pass
    try:
        # Shadow run 은 "무엇을 승격했는가"의 근거다. 테스트가 남긴 승격 기록이 실제 목록에
        # 섞이면 운영 판단의 근거가 오염된다 — 감사로그와 같은 이유로 격리한다.
        from core import shadow_mode
        monkeypatch.setattr(shadow_mode.shadow_mode, "db_path",
                            str(tmp_path / "shadow_runs.db"), raising=False)
    except Exception:
        pass
    try:
        # 프로그램 사용여부도 격리한다 — 테스트가 남긴 비활성화가 실제 DB 에 들어가면
        # **실제 프로그램이 못 쓰게 된다.** 이건 오염이 아니라 사고다.
        from core import program_lifecycle
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "db_path",
                            str(tmp_path / "program_lifecycle.db"), raising=False)
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "_ready", "",
                            raising=False)
    except Exception:
        pass
    try:
        # ★★ [2026-07-30 실측] 기준정보 DB 도 격리한다 — **여기까지 막지 않아 실제로 오염됐다.**
        #   `data/master/master.db` 의 `business_terms` 35건이 전부 `__route_test_term__`
        #   였다(실제 업무 용어는 0건). `tests/test_master_api_routes.py` 가 API 라우트를
        #   호출하고, 라우트는 `master_data` **싱글턴**을 쓰므로 실 DB 에 그대로 쓰였다.
        #   전체 테스트를 한 번 돌릴 때마다 한 건씩 늘어난다(28→35 로 늘어난 것을 관측했다).
        #
        #   ⚠️ 이건 지저분함이 아니라 **거버넌스 지표의 오염**이다. 용어사전·카탈로그는 "전사
        #     표준이 얼마나 정리됐나"의 근거이고, 범위 커버리지(`coverage()`)의 분모다.
        #     테스트가 만든 용어 35건이 "한시 예외 35건"으로 집계되면 이행 일감이 거짓이 된다.
        #
        #   경로만 바꾸면 새 파일에 표가 없어 "no such table" 이 되므로, 세션당 한 번 만든
        #   빈 스키마(`_master_db_template`)를 복사해 붙인다 — 테스트마다 DDL 을 돌리면
        #   전체 실행이 두 배로 늘어난다(88초 → 173초 실측).
        from core import master_data as _md
        _p = tmp_path / "master.db"
        shutil.copyfile(_master_db_template, _p)
        monkeypatch.setattr(_md.master_data, "db_path", str(_p), raising=False)
        monkeypatch.setattr(_md.master_data, "_cache", None, raising=False)
    except Exception as e:
        print(f"⚠️ [conftest] 기준정보 DB 격리 실패(실 DB 오염 위험): {e}")
