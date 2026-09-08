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
import os
import shutil
import tempfile

import pytest

# ════════════════════════════════════════════════════════════════════════════
# ★★★ [2026-08-17 사고] 결정 원장은 **수집이 시작되기 전에** 돌려놓는다.
#
# ⚠️⚠️ autouse fixture 는 늦다. pytest 가 시험 모듈을 **수집**하며 `core.decision_ledger`
#   를 import 하는 순간 전역 싱글턴이 만들어지고, 그때 이미 운영 파일이 열린다 —
#   fixture 는 그 뒤에 돈다. 그래서 격리 지점을 **conftest 모듈 최상단**으로 올린다.
#   conftest 는 시험 모듈보다 먼저 import 된다.
#
# ★ 이것은 «세션 기본값» 이다. 시험마다의 격리는 아래 autouse fixture 가 `tmp_path` 로
#   더 좁게 다시 건다. 두 겹인 이유: fixture 를 어떤 경로로든 우회해도 **운영 파일로는
#   떨어지지 않게** 하기 위해서다.
# ⚠️ `mkdtemp` 는 지우지 않는다 — 세션 중 아무 때나 열릴 수 있고, 지우는 시점을 정확히
#   맞추려다 실패하면 그 순간 운영 경로로 돌아간다. OS 임시 폴더 정리에 맡긴다.
_LEDGER_SESSION_DIR = tempfile.mkdtemp(prefix="afs_ledger_session_")

try:
    from core import decision_ledger as _dl_boot
    from tests.ledger_isolation import isolation_path_error as _path_error_boot

    _boot_db = os.path.join(_LEDGER_SESSION_DIR, "decision_ledger.db")
    _boot_why = _path_error_boot(_boot_db)
    if _boot_why:
        raise RuntimeError(_boot_why)
    _dl_boot._DB_PATH = _boot_db
    _dl_boot.decision_ledger.db_path = _boot_db
except Exception as _boot_err:      # pragma: no cover - 여기서 죽으면 수집 자체가 멈춘다
    # ⚠️ 삼키지 않는다. 격리에 실패한 채 수집이 계속되면 **첫 시험이 운영 원장에 쓴다.**
    raise RuntimeError(
        f"[conftest] 결정 원장 수집 시점 격리에 실패했습니다 — 시험을 시작하지 않습니다: "
        f"{_boot_err}") from _boot_err


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
    """모든 테스트의 런타임 쓰기를 tmp 로 돌린다.

    격리 실패는 경고가 아니라 테스트 중단이다. 계속 진행하면 테스트가 운영 DB나 사용자
    산출물에 쓰면서도 초록이 될 수 있고, 바로 그 fail-open 때문에 clean checkout과 작업
    폴더가 서로 다른 것을 검증했던 사고가 다시 발생한다.
    """
    def isolation_failed(area, exc):
        pytest.fail(f"[conftest] {area} 격리 실패 — 테스트를 실행하지 않음: {exc}",
                    pytrace=False)

    try:
        from core import quality_telemetry
        monkeypatch.setattr(quality_telemetry, "_LOG_PATH",
                            str(tmp_path / "quality_outcomes.jsonl"), raising=False)
    except Exception as e:
        isolation_failed("품질 텔레메트리", e)
    try:
        import core.llm_gateway as gw
        monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH",
                            str(tmp_path / "llm_call_log.jsonl"), raising=False)
    except Exception as e:
        isolation_failed("LLM 호출 로그", e)
    try:
        # 감사로그는 특히 중요하다 — 테스트가 남긴 거부 기록이 섞이면 "실제 침해 시도"를
        # 세는 지표가 오염되고, 반대로 테스트는 남의 기록을 보고 통과할 수 있다(실제 발생).
        from core.enterprise_context import audit
        monkeypatch.setattr(audit, "_LOG_PATH",
                            str(tmp_path / "access_audit.jsonl"), raising=False)
    except Exception as e:
        isolation_failed("접근 감사 로그", e)
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
    except Exception as e:
        isolation_failed("승격·릴리스 준비 저장소", e)
    try:
        # Shadow run 은 "무엇을 승격했는가"의 근거다. 테스트가 남긴 승격 기록이 실제 목록에
        # 섞이면 운영 판단의 근거가 오염된다 — 감사로그와 같은 이유로 격리한다.
        from core import shadow_mode
        monkeypatch.setattr(shadow_mode.shadow_mode, "db_path",
                            str(tmp_path / "shadow_runs.db"), raising=False)
    except Exception as e:
        isolation_failed("Shadow Run 저장소", e)
    try:
        # 프로그램 사용여부도 격리한다 — 테스트가 남긴 비활성화가 실제 DB 에 들어가면
        # **실제 프로그램이 못 쓰게 된다.** 이건 오염이 아니라 사고다.
        from core import program_lifecycle
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "db_path",
                            str(tmp_path / "program_lifecycle.db"), raising=False)
        monkeypatch.setattr(program_lifecycle.program_lifecycle, "_ready", "",
                            raising=False)
    except Exception as e:
        isolation_failed("프로그램 생명주기 저장소", e)
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
        isolation_failed("자산 사용 관측", e)
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
        isolation_failed("ECM 조직도", e)
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
        isolation_failed("범위 정책", e)
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
        # ★★★ [2026-08-15 실측] **조직 디렉터리도 같은 파일을 쓴다 — 그런데 격리에서
        #   빠져 있었다.** `org_directory` 는 `master_data` 와 **다른 싱글턴**이고 자기
        #   `db_path` 를 갖는다(기본값이 운영 `master.db`). 그래서 테스트가 **운영 사용자·
        #   부서를 그대로 읽었다.**
        #
        #   ⚠️⚠️ 그 결과 같은 커밋이 폴더에 따라 다른 답을 냈다: 내 작업트리는 사용자 22·
        #     부서 12 라 권한 강제가 살아 있었고, 깨끗한 checkout 은 0·0 이라
        #     `is_bootstrap()` 이 **전원 무제한**을 돌려줘 경계 시험 255건이 무너졌다.
        #     즉 「전체 통과」가 **코드가 아니라 내 폴더의 데이터**를 증명하고 있었다.
        #
        #   ⚠️ 오염 위험도 함께 있었다 — 조직 API 를 부르는 테스트는 **운영 조직도에 사용자를
        #     쓸 수 있었다.** 실제 인원이 담긴 표다.
        #
        #   ★ 격리하면 기본 상태는 «조직 0» 이다. 권한 경계를 시험하려면 `seeded_org`
        #     fixture 로 **명시해 심는다** — 조직이 없는 상태 자체를 시험하는 것도 있으므로
        #     autouse 로 심지 않는다.
        from core.org_directory import org_directory as _org
        monkeypatch.setattr(_org, "db_path", str(_p), raising=False)
        monkeypatch.setattr(_org, "_scope_cache", {}, raising=False)
    except Exception as e:
        isolation_failed("기준정보·조직 DB", e)
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
        isolation_failed("경영계획 DB", e)
    try:
        # ★★★ [2026-08-08 트랙 I] **생성 앱 데이터 평면도 격리한다.**
        #   `app_data_service` 는 싱글턴이고 라우트가 그것을 쓴다 — 기준정보(`master.db`)가
        #   실제로 오염된 것과 **같은 구조**다(라우트 테스트 → 싱글턴 → 실 DB).
        #   ⚠️ 여기 담기는 것은 업무 데이터다. 오염되면 «이 앱에 데이터가 있다» 는 판단이
        #     거짓이 되고, 그 판단으로 앱의 사용 여부를 결정하게 된다.
        #   스키마 템플릿을 복사하지 않는다 — `ensure_schema()` 가 첫 접근에서 만들고,
        #   표가 2개뿐이라 DDL 비용이 무시할 수준이다(master 는 40여 개라 복사가 필요했다).
        from core import app_data as _ad
        monkeypatch.setattr(_ad.app_data_service._store, "db_path",
                            str(tmp_path / "app_data.db"), raising=False)
        monkeypatch.setattr(_ad.app_data_service._store, "db_path",
                            str(tmp_path / "app_data.db"), raising=False)
        monkeypatch.setattr(_ad.app_data_service._store, "_ready", "", raising=False)

        # ★★★ [I-4 6] **Preview 평면도 격리한다 — 운영과 «다른 파일» 이라는 것이
        #   격리를 대신하지 않는다.** 두 파일 다 `data/` 아래이고, 시험이 Preview 를
        #   쓰기 시작하면 `data/app_data_preview.db` 가 그대로 생긴다.
        # ⚠️ 지연 생성이라 지금은 파일이 안 보인다 — 그 «지금» 에 기대지 않는다.
        #   Preview 를 실제로 쓰는 시험이 하나 생기는 순간 오염이 시작된다.
        # ⚠️ `db_path()` 를 스텁으로 갈아끼우지 않는다 — 그 함수는 **모르는 청중을
        #   거부하는** 것이 일이고, 스텁이 그 성질을 없애면 「모르면 운영」이 된다.
        #   (실제로 그렇게 만들었다가 경계 시험이 즉시 빨개졌다.)
        #   대신 **격리된 인스턴스를 미리 심는다** — `preview_app_data()` 는 이미
        #   만들어져 있으면 그대로 쓴다.
        from core import app_preview as _ap
        from core.app_data import AppDataService as _ADS
        from core.app_data_store import AppDataStore as _ADStore
        monkeypatch.setattr(
            _ap, "_preview_service",
            _ADS(_ADStore(db_path=str(tmp_path / "app_data_preview.db"))),
            raising=False)
    except Exception as e:
        isolation_failed("앱 데이터 평면", e)
    try:
        # ★★★ [2026-08-15 P0-C] **작업 디렉터리 쓰기도 격리한다 — DB 만 막고 있었다.**
        #
        #  실측: 전체 회귀 뒤 실제 작업트리에 다음이 남았다.
        #    projects/__track_g_probe__ · projects/__audit_probe__
        #    skills/_proposals/ · templates/viewer_try.json · agents_registry.prev.json
        #    templates/output_formats.json 의 끝 개행 변경
        #
        #  ⚠️⚠️ 이건 지저분함이 아니다. `projects/__track_g_probe__` 하나 때문에
        #    `test_agent_asset_adapter` 가 **전체 실행에서만** 실패한 적이 있다(혼자 돌면 통과).
        #    「혼자 돌면 통과, 전체로 돌면 실패」의 원인은 순서가 아니라 **남긴 것**이었다.
        #  ⚠️ 그리고 `projects/` 에는 **사용자 산출물**이 들어 있다. 테스트가 그 옆에 쓰는 것은
        #    오염이고, 지우는 코드가 하나라도 잘못 겨누면 사고다.
        #
        #  ★ 지우는 방식이 아니라 **생산 경로 자체를 tmp 로 주입**한다 — 지우는 방식은
        #    「무엇을 지울지」를 매번 맞혀야 하고, 한 번 빗나가면 남거나 남의 것을 지운다.
        from core import paths as _paths
        monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"), raising=False)
        from core import library_paths as _lp
        monkeypatch.setattr(_lp, "_LIBRARY_DIR", str(tmp_path / "library"), raising=False)
        #: ★★★ 템플릿·스킬은 **읽기용 제품 데이터**다(Git 에 있다). 비우면 시험이 다른
        #:   세계를 보게 된다 — 실측: 파일 자산의 `source` 가 `LEGACY` → `SYSTEM` 으로 바뀌어
        #:   마이그레이션 상태 시험이 깨졌다.
        #: ★ 그래서 **사본을 주입**한다: 읽기는 진짜 내용을 보고, 쓰기는 tmp 로 간다.
        from core import agent_registry as _ar
        _tpl = tmp_path / "templates"
        if os.path.isdir(_ar.TEMPLATES_DIR):
            shutil.copytree(_ar.TEMPLATES_DIR, _tpl, dirs_exist_ok=True)
        else:                                      # pragma: no cover - 방어
            _tpl.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(_ar, "TEMPLATES_DIR", str(_tpl), raising=False)
        #: ★★★ **레지스트리 본체도 격리한다.**
        #:   `agents_registry.json` 은 **Git 에 없다**(코드 기본값 `DEFAULT_REGISTRY` 가 정본).
        #:   그런데 `save_registry()` 를 부르는 시험이 저장소 루트에 그 파일을 만들고,
        #:   `agent_asset_adapter._registry_source()` 는 **파일 존재 여부**로 `LEGACY`/`SYSTEM`
        #:   을 가른다.
        #:   ⚠️⚠️ 그래서 「앞선 시험이 파일을 만들었는가」가 뒤 시험의 기대값을 바꿨다 —
        #:     내 트리에서는 있었고 깨끗한 checkout 에는 없었다. 또 하나의 환경 의존이다.
        #:   ★ 있으면 사본을 주고, 없으면 없는 채로 둔다 — 어느 쪽이든 **시험이 명시**한다
        #:     (`file_backed_registry` fixture).
        _reg_path = tmp_path / "agents_registry.json"
        if os.path.exists(_ar.REGISTRY_PATH):
            shutil.copyfile(_ar.REGISTRY_PATH, _reg_path)
        monkeypatch.setattr(_ar, "REGISTRY_PATH", str(_reg_path), raising=False)
        #: 백업본은 **순수 쓰기 대상**이라 사본이 필요 없다.
        monkeypatch.setattr(_ar, "REGISTRY_BACKUP_PATH",
                            str(tmp_path / "agents_registry.prev.json"), raising=False)
        from core import skill_evolution as _se
        _sk = tmp_path / "skills"
        if os.path.isdir(_se.SKILLS_DIR):
            shutil.copytree(_se.SKILLS_DIR, _sk, dirs_exist_ok=True)
        else:                                      # pragma: no cover - 방어
            _sk.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(_se, "SKILLS_DIR", str(_sk), raising=False)
        monkeypatch.setattr(_se, "PROPOSALS_DIR", str(tmp_path / "skill_proposals"),
                            raising=False)
    except Exception as e:
        isolation_failed("작업 디렉터리", e)
    try:
        # ★★★ [2026-08-13 G1-B05] **이중 판정 관측 기록도 격리한다.**
        #   이 표는 「기존 판정을 신규 PDP 로 갈아도 되는가」의 **유일한 근거**다. 테스트가
        #   남긴 표본이 섞이면 실제로는 눌러 보지 않은 시나리오가 «덮였다» 로 읽히고,
        #   그 위조된 근거로 접근 통제를 통째로 갈아 끼우게 된다 — 오염 중 가장 나쁜 종류다.
        #   ⚠️ `_ready` 를 함께 비운다: 이전 경로로 캐시돼 있으면 스키마 생성을 건너뛴다.
        from core import policy_shadow as _ps
        monkeypatch.setattr(_ps.policy_shadow, "db_path",
                            str(tmp_path / "policy_shadow.db"), raising=False)
        monkeypatch.setattr(_ps.policy_shadow, "_ready", "", raising=False)
    except Exception as e:
        isolation_failed("이중 판정 관측", e)
    try:
        # ★★★ [2026-08-17 사고] **결정 원장을 격리한다.**
        #
        # ⚠️⚠️ 이 항목이 여기 «없었다». 그래서 원장에 쓰는 모든 시험이 운영
        #   `data/decision_ledger.db` 에 직접 썼다 — 실측 결과 11,627행 중 99.64%가
        #   시험 계정 패턴이었다. Git 미추적 파일이라 status 오염 검사에도, 지문
        #   감시 목록에도 잡히지 않았다. **감시하지 않는 것은 격리되지 않는다.**
        #
        # 세 곳을 **모두** 바꾼다. 하나라도 빠지면 격리한 줄 알고 운영에 쓴다:
        #   ① `_DB_PATH` — 이후 새로 만들어지는 인스턴스의 기본값
        #   ② 전역 싱글턴 `decision_ledger.db_path` — 이미 만들어진 객체
        #   ③ `_ready` 성격의 캐시가 없으므로 ②로 충분하지만, 소비자 모듈이
        #      `from core.decision_ledger import decision_ledger` 로 **별칭을 이미
        #      들고 있어도** ②가 같은 객체를 가리키므로 함께 따라온다.
        # ⚠️ 생성자 기본 인자를 `_DB_PATH` 로 «굳혀» 두면 ①이 무력해진다 —
        #   파이썬은 기본 인자를 모듈 로딩 때 한 번 평가한다. 그래서 생성자를
        #   `db_path or _DB_PATH` 로 바꿨다(`core/decision_ledger.py`).
        from core import decision_ledger as _dl
        _ledger_db = tmp_path / "decision_ledger.db"
        monkeypatch.setattr(_dl, "_DB_PATH", str(_ledger_db), raising=False)
        monkeypatch.setattr(_dl.decision_ledger, "db_path", str(_ledger_db), raising=False)
        #: ★ 격리가 «진짜로» 임시 경로인지 여기서 확인한다. 운영 `data/` 아래로
        #:   해석되면 그 순간 멈춘다 — 경로 계산이 틀린 채 계속 가면 그것이 곧
        #:   이번 사고의 재발이다.
        #: ⚠️ 판정은 `tests/ledger_isolation.py` 에 둔다. conftest 안에만 두면
        #:   **시험이 그 규칙을 부를 수 없고**, 규칙을 지워도 아무것도 안 깨진다.
        from tests.ledger_isolation import isolation_path_error
        _why = isolation_path_error(str(_ledger_db))
        if _why:
            raise RuntimeError(_why)
    except Exception as e:
        isolation_failed("결정 원장", e)
    try:
        # ★★★ [BDR-2] 업무 데이터 준비 저장소도 **처음부터** 격리한다.
        #
        # ⚠️ 결정 원장은 격리 목록에 없어서 11,633행이 오염됐다. 새 저장소를 만들 때
        #   격리를 나중으로 미루면 같은 일이 반복된다 — 목록에 넣는 것이 저장소를
        #   만드는 일의 일부다.
        # ⚠️ 여기도 **두 곳**을 바꾼다: 모듈 기본값과 이미 만들어진 전역 싱글턴.
        from core.data_preparation import store as _dp
        _dp_db = tmp_path / "data_preparation.db"
        monkeypatch.setattr(_dp, "_DB_PATH", str(_dp_db), raising=False)
        monkeypatch.setattr(_dp.data_preparation_store, "db_path", str(_dp_db),
                            raising=False)
        monkeypatch.setattr(_dp.data_preparation_store, "_prepared_for", None,
                            raising=False)
    except Exception as e:
        isolation_failed("업무 데이터 준비 저장소", e)

    try:
        # ★★★ [2026-08-23 실측] **협업 저장소가 격리 목록에 없었다.**
        #
        # ⚠️⚠️ 바로 위 주석이 「결정 원장은 격리 목록에 없어서 11,633행이 오염됐다」라고
        #   적어 놓았는데, **같은 일이 여기서 반복됐다.** 운영 `data/collaboration.db` 에
        #   결정 안건 253행·발간물 76행이 쌓여 있었고, 그중 237행은 시험 계정
        #   `owner@afs.invalid` 가 만든 것이다 — 시험이 운영 자료를 만들고 있었다.
        #
        # ★ 더 나쁜 것: 불변식 검사기도 이 파일을 **안 보고 있어서** 「운영 데이터 영역이
        #   회귀 전과 같습니다」라고 초록을 냈다. 통제 둘이 같은 자리를 비워 두면 그
        #   자리는 아무도 안 본다.
        # ⚠️ 여기도 **두 곳**을 바꾼다: 모듈 기본값과 이미 만들어진 전역 싱글턴.
        from core import collaboration_store as _cs
        _cs_db = tmp_path / "collaboration.db"
        monkeypatch.setattr(_cs, "_DB_PATH", str(_cs_db), raising=False)
        monkeypatch.setattr(_cs.collaboration_store, "db_path", str(_cs_db),
                            raising=False)
        for _attr in ("_prepared_for", "_ready", "_ensured"):
            if hasattr(_cs.collaboration_store, _attr):
                monkeypatch.setattr(_cs.collaboration_store, _attr, None, raising=False)
    except Exception as e:
        isolation_failed("협업 저장소(결정 안건·발간)", e)

    try:
        # ★★★ [2026-09-08 F-0 탐침이 찾아냈다] 수집 저장소·원문 보관소가 **격리되지
        #   않고 있었다.** 싱글턴이 운영 `data/external_intelligence.db` 를 직접 열어,
        #   API 시험이 만든 수집 작업 **80건이 운영 DB 에 쌓였다**(09-06~09-08).
        #   ⚠️ 「시험은 격리된다」는 믿음이 여기서 깨졌다 — 격리는 저장소마다 «명시»해야 한다.
        from core.external_intelligence import acquisition_store as _aq
        _aq_db = tmp_path / "external_intelligence.db"
        monkeypatch.setattr(_aq, "_DB_PATH", str(_aq_db), raising=False)
        monkeypatch.setattr(_aq.acquisition_store, "db_path", str(_aq_db), raising=False)
        monkeypatch.setattr(_aq.acquisition_store, "_ready_done", False, raising=False)
        from core.external_intelligence import raw_store as _rs
        monkeypatch.setattr(_rs.raw_store, "root", str(tmp_path / "external_raw"),
                            raising=False)
    except Exception as e:
        isolation_failed("수집 저장소·원문 보관소", e)

    try:
        # ⚠️ LLM 캐시는 `core/paths.py` 를 안 거치고 자기 경로를 조립했다(고쳤다).
        #   그래도 **import 시점에 `_init_db()`** 를 부르므로, 뿌리를 안 돌리면 시험이
        #   운영 `data/llm_cache.db` 를 만든다.
        import core.paths as _paths
        monkeypatch.setattr(_paths, "DATA_DIR", str(tmp_path), raising=False)
    except Exception as e:
        isolation_failed("데이터 뿌리(DATA_DIR)", e)


# ── [P0-A/B] 조직·강제 상태를 **명시**하는 fixture ────────────────────────
#
# ★★★ 왜 autouse 가 아닌가: 「조직이 아직 없다」는 상태 자체를 시험하는 것들이 있다
#   (부트스트랩 잠금 방지·미바인딩 비노출). 전부에 심으면 그 시험들이 조용히 의미를 잃는다.

@pytest.fixture()
def seeded_org(monkeypatch):
    """★★★ **테스트 전용 조직도**를 격리 저장소에 심는다.

    ⚠️ 이것 없이 권한 경계를 시험하면 `is_bootstrap()` 이 전원 무제한을 돌려주므로
      **막히는지 확인하려는 그 통제가 애초에 꺼져 있다.**

    돌려주는 값에는 부서·사용자 목록과 신원 상수가 들어 있다 —
    시험이 `hikwon_17@lsmnm.com` 같은 **실존 계정을 적지 않게** 하기 위해서다."""
    from core.enterprise_context.repository import ecm_repository
    from core.org_directory import org_directory
    from tests import org_seed
    org_seed.seed(org_directory)
    #: ⚠️ ECM 노드까지 심어야 부서가 «범위에 묶인» 상태가 된다. 비우면 D-014 로 **모든 쓰기가
    #:   막히고**, 시험은 「권한 없음」과 「범위 없음」을 구분하지 못한 채 빨강이 된다.
    org_seed.seed_ecm(ecm_repository, org_directory)
    org_directory._invalidate()
    return org_seed


@pytest.fixture()
def enforced_org(seeded_org, monkeypatch, tmp_path):
    """조직도 + **권한 강제 ON**.

    ★★★ 강제를 **정책 파일**로 켠다. `config.ORG_ENFORCE` 를 직접 monkeypatch 하면
      제품이 실제로 읽는 경로(`scope_policy`)를 지나지 않아, 시험과 실서버가 **다른 세계**가
      된다 — `api/deps.current_principal` 의 주석이 그 사고를 그대로 적어 두었다.

    ⚠️ 정책 파일은 conftest 가 이미 `tmp_path` 로 격리했다. 여기서 **값을 명시**하지 않으면
      코드 기본값 `False` 로 떨어지고, 그때 경계 시험은 전부 무제한 모드에서 통과한다."""
    import json

    from core import scope_policy
    path = tmp_path / "scope_policy.json"
    body = {}
    if path.exists():
        try:
            body = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            body = {}
    body["org_enforce"] = True
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(scope_policy, "_POLICY_PATH", str(path), raising=False)
    assert scope_policy.org_enforce() is True, "강제를 켰는데 정책이 읽히지 않는다"
    from core.org_directory import org_directory
    org_directory._invalidate()
    return seeded_org


@pytest.fixture()
def empty_org_bootstrap():
    """★★★ **조직 0건**을 «의도적으로» 선언한다.

    ⚠️⚠️ 이 상태에서는 `is_bootstrap()` 이 **전원 무제한**을 돌려준다. 그것 자체는 옳다 —
      조직을 세우기도 전에 권한을 강제하면 첫 관리자를 만들 사람이 아무도 없어 잠긴다.

    ★★★ 그러나 **일반 권한 시험에 이 상태가 섞이면 그 시험은 아무것도 검증하지 못한다.**
      막히는지 보려는 통제가 애초에 꺼져 있고, 시험은 초록이다. 2026-08-15 에 정확히 그
      일이 있었다(깨끗한 checkout 255건).

    그래서 이 fixture 는 **부트스트랩 자체를 검증하는 시험만** 쓴다. 조직이 필요한 시험은
    `seeded_org`(조직·권한 경계) 또는 `enforced_org`(강제 정책)를 **명시적으로** 고른다 —
    셋 중 하나를 고르지 않은 권한 시험은 「무엇을 전제하는지 아무도 모르는」 시험이다."""
    from core.org_directory import org_directory
    org_directory._invalidate()
    assert org_directory.is_bootstrap(), (
        "조직이 남아 있다 — 이 fixture 는 «조직 0건» 을 전제한다. 격리가 새고 있는지 확인할 것")
    return org_directory


@pytest.fixture()
def file_backed_registry():
    """★★★ 레지스트리를 **파일에서 온 것**(`LEGACY`)으로 만든다.

    `agent_asset_adapter._registry_source()` 는 `agents_registry.json` 의 **존재 여부**로
    `LEGACY`/`SYSTEM` 을 가른다. 그 파일은 Git 에 없으므로 기본은 `SYSTEM` 이다.

    ⚠️ 예전에는 이것을 선언하지 않았고, **앞선 시험이 남긴 파일**이 뒤 시험의 기대값을
      정했다. 그래서 같은 커밋이 폴더에 따라 다른 답을 냈다 — 무엇을 전제하는지 적는다."""
    from core import agent_registry as _ar
    _ar.save_registry(_ar.load_registry())
    assert os.path.exists(_ar.REGISTRY_PATH)
    return _ar.REGISTRY_PATH


# ── [2026-08-17 사고 · P0-L2] 세션 전체를 감시한다 ──────────────────────
@pytest.fixture(scope="session", autouse=True)
def _live_ledger_must_not_move():
    """세션 **시작과 끝**에 운영 원장의 논리적 상태를 대조한다.

    ★★★ 개별 시험의 앞뒤만 보면 «격리 fixture 가 걸리지 않은 시험»과 «수집 단계의
      쓰기» 를 못 잡는다. 이번 사고의 두 번째 원인이 정확히 수집 단계였다.

    ⚠️ 실패해도 시험을 되돌릴 수는 없다 — 이미 쓴 뒤다. 그래도 **알리는 것**이
      모르는 것보다 낫다. 모르면 다음 사람이 그 오염 위에 또 쌓는다.
    """
    from tests.ledger_isolation import live_sentinel, live_side_files

    before, files_before = live_sentinel(), live_side_files()
    yield
    after, files_after = live_sentinel(), live_side_files()
    assert after == before, (
        f"⛔ 이 시험 세션이 **운영 결정 원장을 바꿨습니다.**\n"
        f"   전: {before}\n   후: {after}\n"
        f"   격리를 타지 않은 경로가 있습니다 — 무엇이 썼는지 찾아야 합니다.")
    assert files_after == files_before, (
        f"⛔ 이 시험 세션이 운영 원장의 WAL/SHM 파일을 만들었거나 지웠습니다.\n"
        f"   전: {files_before}\n   후: {files_after}")
