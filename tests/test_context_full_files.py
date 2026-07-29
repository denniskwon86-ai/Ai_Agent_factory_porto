"""core/context_engine.py — 증분 codegen 전체파일 주입 검증.
소유 파일(full_file_exts)은 절단 없이 전체 주입되어 멀티태스크 기능 누락(회귀)을 막아야 한다.
full_file_exts 미지정 시에는 종전과 동일하게 per_file 절단되어야 한다(비개발자 단계 회귀 방지)."""
import pytest

from state_models import ProjectState
from core.context_engine import ContextEngine

SENTINEL = "ZZZ_END_OF_FILE_SENTINEL_ZZZ"


@pytest.fixture(autouse=True)
def _isolate_external_context(monkeypatch):
    """★ [2026-07-29] 컨텍스트의 **외부 입력 세 곳을 끊는다** — 기준정보 DB·지식팩·기업 프로필.

    ⚠️ 왜 필요한가(실측): 이 파일의 테스트들은 실제 `data/master/master.db` 를 읽고 있었다.
      개발 DB 가 비어 있으면 기준정보 블록이 0자가 되어 **예산을 삼키는 회귀를 못 잡고**,
      반대로 DB 가 커지면 무관한 이유로 파일 주입 검증이 깨진다. 어느 쪽이든 "테스트는 통과했는데
      실제로는 깨져 있는" 상태를 만든다(2026-07-29 결함 4의 부수 발견, 인계 문서 §4-2 2-1).

    이 파일이 검증하려는 것은 **파일·기술명세 주입 규칙**이지 기준정보 내용이 아니다.
    기준정보가 예산을 삼키는 회귀는 아래 `test_master_block_cannot_starve_the_rest` 가
    거대한 블록을 **직접 주입해** 따로 잠근다(개발 DB 상태와 무관하게)."""
    import core.context_engine as ce

    class _NoMaster:
        def get_master_context(self, state, max_chars=-1):
            return ""

    class _NoKnowledge:
        def get_relevant_context(self, state):
            return ""

        def get_grounding_context(self, state):
            return ""

    class _NoProfile:
        def get_company_profile(self):
            return {}

    monkeypatch.setattr(ce, "master_data", _NoMaster())
    monkeypatch.setattr(ce, "knowledge_base", _NoKnowledge())
    monkeypatch.setattr(ce, "persona_learner", _NoProfile())


def _make_state(tmp_path):
    # 4000자를 크게 초과하는 .tsx + 작은 .py 를 디스크에 쓰고 file_index 에 등록
    big_tsx = "// App\n" + ("const filler = 1;\n" * 400) + f"\n// {SENTINEL}\n"
    assert len(big_tsx) > 4000
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "App.tsx").write_text(big_tsx, encoding="utf-8")
    (tmp_path / "backend").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backend" / "main.py").write_text("print('be')\n", encoding="utf-8")

    return ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": str(tmp_path),
        "file_index": {
            "src/App.tsx": {"path": "src/App.tsx", "purpose": "메인 화면"},
            "backend/main.py": {"path": "backend/main.py", "purpose": "API 서버"},
        },
    })


def test_owned_file_injected_in_full(tmp_path):
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx", ".ts"))
    # 소유 .tsx 는 전체 주입 → 끝부분 sentinel 이 살아 있고 절단 마커가 없어야 한다
    assert SENTINEL in ctx
    assert "전체 코드 보존 필수" in ctx
    # 비소유 .py 는 본문 없이 1줄 색인(참조)으로만
    assert "본 작업 비대상" in ctx
    assert "print('be')" not in ctx


def test_default_mode_truncates_large_file(tmp_path):
    # full_file_exts 미지정 → 종전대로 per_file(4000) 절단 (sentinel 소실, 절단 마커 존재)
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state)
    assert SENTINEL not in ctx
    # 절단/요약 증거: 코드 파일은 JIT 시그니처 요약, 그 외는 _clip 절단 마커 중 하나가 있어야 한다
    assert ("(JIT Signature)" in ctx) or ("자 생략" in ctx)


def test_light_mode_skips_files(tmp_path):
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state, light=True, full_file_exts=(".tsx",))
    # light=True 면 파일 주입 자체를 생략
    assert SENTINEL not in ctx
    assert "워크스페이스 실제 파일" not in ctx


def test_disk_walk_recovers_owned_file_missing_from_index(tmp_path):
    # file_index 가 비어 있어도(유실/stale) 소유 확장자 파일은 디스크에서 직접 발견·주입돼야 한다
    big_tsx = "// App\n" + ("const filler = 1;\n" * 400) + f"\n// {SENTINEL}\n"
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "App.tsx").write_text(big_tsx, encoding="utf-8")
    state = ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": str(tmp_path),
        "file_index": {},  # 인덱스 유실 상황
    })
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx", ".ts"))
    assert SENTINEL in ctx  # 인덱스에 없어도 디스크 walk 로 복구 주입
    assert "전체 코드 보존 필수" in ctx


def test_disk_walk_excludes_noise_dirs(tmp_path):
    # node_modules 등 제외 디렉터리의 owned 확장자는 주입하지 않는다
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "node_modules" / "pkg" / "index.tsx").write_text(f"// {SENTINEL}_NOISE\n", encoding="utf-8")
    state = ProjectState.model_validate({
        "project_name": "T", "workspace_root": str(tmp_path), "file_index": {},
    })
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx",))
    assert f"{SENTINEL}_NOISE" not in ctx


# --- [R1] 실행단계 컨텍스트 다이어트: tech_spec 섹션 필터 ---
import json as _json

# FE/API 계약/DB 세 섹션을 가진 기술사양. 각 본문에 고유 sentinel.
_TECH_SPEC = """# Overview
OVERVIEW_SENT

# Frontend UI
FE_SENT

# Backend API Endpoints
API_SENT: GET /api/orders -> {id, total}

# Database Schema
DB_SENT: CREATE TABLE orders(...)
"""


def _tech_spec_state(tmp_path, required_agents):
    """실행단계(비기획) + WBS 태스크(required_agents) + tech_spec 를 갖춘 상태."""
    wbs = {"tasks": [{"task_id": "WBS-001", "title": "t",
                      "required_agents": required_agents}]}
    (tmp_path / "00_wbs_master_plan.json").write_text(
        _json.dumps(wbs, ensure_ascii=False), encoding="utf-8")
    return ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": str(tmp_path),
        "current_stage": "BUILD",          # 비기획 → 다이어트 활성
        "current_sprint_task_id": "WBS-001",
        "tech_spec_summary": _TECH_SPEC,
        "file_index": {},
    })


def test_tech_spec_fe_task_keeps_api_contract_drops_db(tmp_path):
    # FE 전담 태스크: API 계약(프론트가 호출할 엔드포인트)은 유지, 순수 DB 스키마는 제거
    state = _tech_spec_state(tmp_path, ["Frontend"])
    ctx = ContextEngine.build_core_context(state, light=True)
    assert "FE_SENT" in ctx          # 자기 담당
    assert "API_SENT" in ctx         # ★ R1 핵심: FE 도 API 계약은 반드시 봐야 함
    assert "OVERVIEW_SENT" in ctx    # 공용 섹션 유지
    assert "DB_SENT" not in ctx      # 순수 백엔드 구현 세부는 제거


def test_tech_spec_be_task_drops_fe_keeps_api(tmp_path):
    # BE 전담 태스크: FE 섹션 제거, API/DB 유지
    state = _tech_spec_state(tmp_path, ["Backend", "DB"])
    ctx = ContextEngine.build_core_context(state, light=True)
    assert "FE_SENT" not in ctx
    assert "API_SENT" in ctx
    assert "DB_SENT" in ctx


def test_tech_spec_fullstack_task_keeps_all(tmp_path):
    # 풀스택 태스크(FE+BE): 아무것도 버리지 않음
    state = _tech_spec_state(tmp_path, ["Frontend", "Backend"])
    ctx = ContextEngine.build_core_context(state, light=True)
    assert "FE_SENT" in ctx
    assert "API_SENT" in ctx
    assert "DB_SENT" in ctx


# ── 기준정보가 기술 명세를 굶기지 않는가 (2026-07-29 실측 회귀) ──────────────
def test_master_block_cannot_starve_the_rest(tmp_path, monkeypatch):
    """★★ 기준정보 블록이 컨텍스트 예산 전체를 삼켜 **기술 명세가 사라진 회귀**를 잠근다.

    D-010 으로 주입 상한을 없앤 뒤, 도메인·조직범위가 선언되지 않은 프로젝트에서 "전수"가 곧
    "DB 전체"가 되어 실측 70건 = 21,877자 > 예산 20,000자가 됐다. 뒤에 붙는 기술 명세가 통째로
    잘려 **코더가 API 계약을 못 봤다.**

    ⚠️ 이 테스트는 개발 DB 상태에 의존하지 않는다 — 거대한 블록을 직접 주입해 검증한다.
      (원래 이 파일의 다른 테스트들은 실제 `data/master/master.db` 를 읽으므로, DB 가 비어 있으면
       회귀를 못 잡는다. 그래서 별도로 잠근다.)"""
    import core.context_engine as ce

    seen = {}

    class _Fat:
        def get_master_context(self, state, max_chars=-1):
            seen["max_chars"] = max_chars
            block = "[기준정보] " + ("X" * 60_000)
            # 호출자가 준 예산을 지키는 척하지 않는다 — 예산을 안 주면 다 뱉는다.
            if isinstance(max_chars, int) and max_chars > 0:
                return block[:max_chars]
            return block

    monkeypatch.setattr(ce, "master_data", _Fat())
    state = _tech_spec_state(tmp_path, ["Frontend", "Backend"])
    ctx = ContextEngine.build_core_context(state, light=True)

    assert isinstance(seen.get("max_chars"), int) and seen["max_chars"] > 0, \
        "ContextEngine 이 기준정보에 예산을 배정하지 않았다(배선 누락)"
    assert "API_SENT" in ctx, "기준정보가 기술 명세를 밀어냈다"
    assert "FE_SENT" in ctx and "DB_SENT" in ctx
