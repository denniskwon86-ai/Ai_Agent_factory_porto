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


@pytest.fixture(scope="session")
def _planning_db_template(tmp_path_factory):
    """빈 경영계획 스키마를 **세션당 한 번** 만든다(기준정보와 같은 이유 — DDL 비용).

    ★★ [2026-08-05] 왜 격리하는가: `data/planning.db` 는 격리 목록에 없어 **테스트가 운영
      경영계획 DB 를 그대로 쓰고 있었다.** 계정과목·실적·시나리오·제출물이 들어 있는 파일이다.
      실제로 통제 확인 중에 탐침 데이터가 그 DB 에 들어갔고(계정과목·동인·fact·시나리오·제출물),
      지우고 복구해야 했다. 경로를 절대경로로 고정한 뒤에는 cwd 와 무관하게 **항상** 그 파일을
      쓰게 되므로, 격리를 여기서 확실히 한다.
    ⚠️ 경영계획은 «거버넌스 지표의 오염» 보다 나쁘다 — 매출·원가 전망이 담기는 표다."""
    p = tmp_path_factory.mktemp("planning_tpl") / "planning.db"
    from core.planning_model import PlanningStore
    PlanningStore(db_path=str(p))        # DDL·컬럼 마이그레이션 1회
    import sqlite3
    conn = sqlite3.connect(str(p))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return str(p)


@pytest.fixture()
def ecm_org_seed():
    """[D-018] 격리 ECM 에 **운영 조직 코드에 대응하는 최소 노드**를 심는다(autouse 아님).

    ★★★ 왜 필요한가 — **격리가 반쪽이다.** `enterprise_context.db`(ECM 조직도)는 위에서 tmp 로
      격리하지만 `org_directory`(부서·사용자·권한)는 **운영 DB 를 그대로 읽는다.** 그래서
      사용자의 `readable_scope_nodes` 는 실제 값인데 ECM 에는 그 노드가 없는 상태가 된다.

      백필(D-018 ⑤) 전에는 그 비대칭이 드러나지 않았다: 양쪽이 다 코드(`LS_MNM`)였으니
      코드끼리 비교돼 통과했다. 백필로 `departments.scope_node_id` 가 `node_*` 로 승격되자
      **자산 가시성 테스트 15건이 404 로 깨졌다** — 사용자 범위는 정본인데 테스트가 만든 자산의
      소유는 코드이고, ECM 이 비어 있어 둘을 잇는 조상·별칭 해석이 불가능했기 때문이다.

    ⚠️ autouse 로 두지 않는다. 조직도가 **없는** 상태를 검증하는 테스트도 있고(미바인딩 비노출),
      전부에 심으면 그 테스트가 조용히 의미를 잃는다.
    ⚠️⚠️ **노드를 새로 만들지 않고 운영 조직도에서 복사한다.** 백필 전에는 새로 만들어도 됐다
      (양쪽이 코드였으므로 코드끼리 매칭). 백필 후 `readable_scope_nodes` 는 **운영 ECM 의
      `node_*`** 를 가리키므로, 격리 DB 에 새 id 를 만들면 **절대 매칭되지 않는다**
      (실측: 격리 `LS_MNM`=`node_a553…` vs 운영 `departments`=`node_4140…` → 생성 403).
      그래서 필요한 노드만 **id 째로** 복사한다.
    ⚠️ 운영 DB 는 **읽기 전용**으로 연다. 그리고 필요한 코드가 없으면 조용히 넘기지 않고
      그 사실이 테스트 실패로 드러나게 둔다 — skip 으로 덮으면 통제 검증이 사라진다.
    """
    import os
    import sqlite3

    from core.enterprise_context.models import STATUS_ACTIVE
    from core.enterprise_context.repository import ecm_repository as repo
    from core.paths import data_path

    # conftest 는 **경로만** tmp 로 바꾼다(스키마는 만들지 않는다). 쓰기는 `conn.execute` 를
    # 직접 하므로 «no such table» 이 되고, 읽기(`_query`)만 실패 시 DDL 을 돌린다.
    repo.list_nodes()

    src_path = data_path("enterprise_context.db")
    if not os.path.exists(src_path):
        return {}
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(repo.db_path)
    out = {}
    try:
        ents = {r["entity_id"]: dict(r) for r in src.execute(
            "SELECT * FROM enterprise_entities")}
        nodes = [dict(r) for r in src.execute(
            "SELECT * FROM organization_nodes WHERE status=?", (STATUS_ACTIVE,))]
        keep = {n["node_id"] for n in nodes}
        # 참조되는 엔티티만 복사한다(가상 엔티티의 base 까지 함께 — 제약이 요구한다).
        need_ents = {n["entity_id"] for n in nodes}
        need_ents |= {ents[e]["base_entity_id"] for e in list(need_ents)
                      if e in ents and ents[e].get("base_entity_id")}
        for eid in need_ents:
            e = ents.get(eid)
            if not e:
                continue
            cols = ",".join(e.keys())
            dst.execute(f"INSERT OR REPLACE INTO enterprise_entities ({cols}) "
                        f"VALUES ({','.join('?' * len(e))})", tuple(e.values()))
        for n in nodes:
            cols = ",".join(n.keys())
            dst.execute(f"INSERT OR REPLACE INTO organization_nodes ({cols}) "
                        f"VALUES ({','.join('?' * len(n))})", tuple(n.values()))
            out[n["code"]] = n["node_id"]
        for r in src.execute("SELECT * FROM organization_edges WHERE status=?",
                             (STATUS_ACTIVE,)):
            d = dict(r)
            if d["from_node_id"] not in keep or d["to_node_id"] not in keep:
                continue        # 끊긴 엣지는 옮기지 않는다 — 없는 노드를 가리키면 상속이 깨진다
            cols = ",".join(d.keys())
            dst.execute(f"INSERT OR REPLACE INTO organization_edges ({cols}) "
                        f"VALUES ({','.join('?' * len(d))})", tuple(d.values()))
        dst.commit()
    finally:
        src.close()
        dst.close()
    return out


@pytest.fixture(autouse=True)
def _isolate_runtime_telemetry(tmp_path, monkeypatch, _master_db_template,
                               _planning_db_template):
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
        # ★★ [2026-08-07 P4-4] **자산 사용 관측도 격리한다.**
        #   `agent_registry.agent_skill()` 과 `resolve_workflow()` 가 해석 시점에 기록하는데,
        #   이 둘은 스위트 전반에서 불린다. 격리하지 않으면 **테스트가 운영 관측 기록을 만든다**
        #   — 그러면 「이 자산이 쓰이는가」의 답이 테스트 때문에 바뀌고, P4-4 의 정리 제안이
        #   테스트 흔적을 근거로 나온다.
        #   ⚠️ `db_path` 만 바꾸면 안 된다: `_ready` 가 이전 경로로 캐시돼 있으면 스키마 생성을
        #     건너뛰고, 메모리 누적(`_pending`)은 이전 테스트 것이 남는다.
        from core import asset_usage as _au
        monkeypatch.setattr(_au.asset_usage, "db_path",
                            str(tmp_path / "asset_usage.db"), raising=False)
        monkeypatch.setattr(_au.asset_usage, "_ready", "", raising=False)
        monkeypatch.setattr(_au.asset_usage, "_pending", {}, raising=False)
    except Exception as e:
        print(f"⚠️ [conftest] 자산 사용 관측 격리 실패(운영 기록 오염 위험): {e}")
    try:
        # ★★ [2026-07-31 실측] **ECM 조직도(enterprise_context.db)도 격리한다.**
        #   이것이 없으면 테스트가 **운영 조직도에 의존**한다. 실측: 참고문서 가시성 테스트가
        #   워크트리(조직도 0건)에서는 통과하고 원래 폴더(조직도 9건)에서는 실패했다 —
        #   `MNM_BATTERY` 의 조상 `LS_MNM` 이 해석되면 상속으로 자산이 하나 더 보이기 때문이다.
        #   즉 같은 코드가 **폴더에 따라 다른 결과**를 낸다(오늘 아침 업무표준 테스트와 같은 유형).
        #   ⚠️ 조직도에 의존하는 테스트는 두 방향으로 거짓말한다: 없는 환경에서는 통제가 약해
        #     보이고, 있는 환경에서는 상속이 끼어들어 기대와 달라진다.
        from core.enterprise_context import repository as _ecm_repo
        monkeypatch.setattr(_ecm_repo.ecm_repository, "db_path",
                            str(tmp_path / "enterprise_context.db"), raising=False)
    except Exception as e:
        print(f"⚠️ [conftest] ECM 조직도 격리 실패(테스트가 운영 조직도에 좌우됨): {e}")
    try:
        # ★★ [2026-07-30 실측] **범위 정책 저장소**도 격리한다.
        #   이 파일은 `ORG_ENFORCE`·한시예외 만료일을 담고, `resolve_scope` 와 만료 판정이
        #   **코드 기본값보다 먼저** 읽는다. 그래서 저장소에 파일이 하나 있으면
        #   `monkeypatch.setattr(config, "ORG_ENFORCE", True)` 가 **조용히 무력화**된다
        #   (실측: 그 상태로 test_org_directory 9건이 깨졌다 — 테스트가 코드를 검증하는 게
        #   아니라 로컬 파일을 검증하게 된다).
        from core import scope_policy
        monkeypatch.setattr(scope_policy, "_POLICY_PATH",
                            str(tmp_path / "scope_policy.json"), raising=False)
    except Exception as e:
        print(f"⚠️ [conftest] 범위 정책 격리 실패(테스트가 로컬 정책 파일에 좌우됨): {e}")
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
    try:
        # ★★★ [2026-08-05] **경영계획 DB 도 격리한다 — 여기까지 막지 않아 실제로 오염됐다.**
        #   통제 확인 중 탐침 데이터가 `data/planning.db` 에 들어갔다(계정과목·동인·fact·
        #   시나리오·제출물). 지우고 복구했지만, 애초에 테스트가 운영 DB 를 쓰지 않아야 한다.
        #   ⚠️ 기준정보 오염보다 무겁다 — 매출·원가 전망이 담기는 표다.
        #   `planning_approval`·`planning_drivers` 도 모두 `planning_store._connect()` 를 쓰므로
        #   **싱글턴의 `db_path` 하나만 바꾸면 계열 전체가 격리된다.**
        from core import planning_model as _pm
        _pp = tmp_path / "planning.db"
        shutil.copyfile(_planning_db_template, _pp)
        monkeypatch.setattr(_pm.planning_store, "db_path", str(_pp), raising=False)
    except Exception as e:
        print(f"⚠️ [conftest] 경영계획 DB 격리 실패(실 DB 오염 위험): {e}")
