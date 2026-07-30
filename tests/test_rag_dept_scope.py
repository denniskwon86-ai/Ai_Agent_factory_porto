# ==========================================
# 과거사례 RAG 부서 스코프 (설계서 Phase 5 — LLM 프롬프트/검색 경로 권한)
#
# 이 경로가 설계서가 지목한 **최대 유출 경로**였다: 전역 `project_releases` 컬렉션을
# 필터도 임계값도 없이 검색해 상위 N건을 모든 프롬프트에 주입했다.
#
# 검증하는 계약 넷:
#  ① `_meta_matches` 는 **모르는 연산자를 통과시키지 않는다**(fail-closed). 필터를 이해하지
#     못한 채 통과시키면 그게 곧 유출이다.
#  ② `search_similar(where=)` 는 엔진이 `$in` 을 못 받으면 over-fetch 후 파이썬에서 거른다.
#     폴백이 조용히 필터를 포기하면 안 된다.
#  ③ `get_relevant_context` 3중 방어(부서 체인 / 거리 임계값 / 킬스위치).
#  ④ ★ **배선**: 게시 경로가 `owner_dept_id` 를 인덱싱 메타로 넘겨야 한다. 이게 빠지면
#     청크가 전부 미태깅으로 들어가고 ③의 fail-closed 필터가 자기 부서 산출물까지
#     전부 배제한다 — 오류 없이 과거사례 RAG 가 0건이 된다(실제로 그 상태였다).
# ==========================================
import json
import os
import sys
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.factory_control as fc
import config
from api.deps import Principal, current_principal
from core.knowledge_base import KnowledgeBase, _meta_matches
from core.org_directory import AccessScope


# ── ① `_meta_matches` — Chroma where 절의 파이썬 폴백 ─────────────────────
def test_equality_and_missing_key():
    assert _meta_matches({"owner_dept_id": "sales"}, {"owner_dept_id": "sales"})
    assert not _meta_matches({"owner_dept_id": "rnd"}, {"owner_dept_id": "sales"})
    assert not _meta_matches({}, {"owner_dept_id": "sales"}), "키가 없으면 배제"


def test_empty_where_matches_everything():
    assert _meta_matches({"a": 1}, {})
    assert _meta_matches({"a": 1}, None)


def test_in_operator():
    w = {"owner_dept_id": {"$in": ["hq", "quality"]}}
    assert _meta_matches({"owner_dept_id": "quality"}, w)
    assert not _meta_matches({"owner_dept_id": "sales"}, w)
    assert not _meta_matches({"owner_dept_id": ""}, w), "레거시 미태깅은 배제(fail-closed)"


def test_eq_ne_operators():
    assert _meta_matches({"x": "a"}, {"x": {"$eq": "a"}})
    assert not _meta_matches({"x": "b"}, {"x": {"$eq": "a"}})
    assert _meta_matches({"x": "b"}, {"x": {"$ne": "a"}})
    assert not _meta_matches({"x": "a"}, {"x": {"$ne": "a"}})


def test_or_and_composition():
    w_or = {"$or": [{"owner_dept_id": "sales"}, {"owner_dept_id": "hq"}]}
    assert _meta_matches({"owner_dept_id": "hq"}, w_or)
    assert not _meta_matches({"owner_dept_id": "rnd"}, w_or)

    w_and = {"$and": [{"owner_dept_id": "hq"}, {"filename": "prd.md"}]}
    assert _meta_matches({"owner_dept_id": "hq", "filename": "prd.md"}, w_and)
    assert not _meta_matches({"owner_dept_id": "hq", "filename": "rfp.md"}, w_and)


def test_dept_and_filename_and_combination():
    """설계서 356행 — dept 필터는 `filename` 필터와 AND 결합해서도 쓴다(Phase 8-2 PRD 대조)."""
    w = {"owner_dept_id": {"$in": ["hq", "quality"]}, "filename": "prd.md"}
    assert _meta_matches({"owner_dept_id": "quality", "filename": "prd.md"}, w)
    assert not _meta_matches({"owner_dept_id": "quality", "filename": "qa_report.md"}, w)
    assert not _meta_matches({"owner_dept_id": "sales", "filename": "prd.md"}, w)


def test_unknown_operator_is_excluded_not_passed():
    """★ fail-closed — 이해하지 못한 필터를 통과시키면 그게 유출이다."""
    assert not _meta_matches({"n": 5}, {"n": {"$gt": 1}})
    assert not _meta_matches({"n": 5}, {"n": {"$nin": [9]}})


# ── ② `search_similar(where=)` 와 폴백 ────────────────────────────────────
class _FakeCollection:
    """Chroma 컬렉션 대역. `support_where=False` 면 `where` 를 받으면 터진다."""

    def __init__(self, rows, support_where=True):
        self.rows = rows                 # [(content, meta, distance), ...]
        self.support_where = support_where
        self.calls = []
        self.added = []

    def query(self, query_texts=None, n_results=5, include=None, where=None):
        self.calls.append({"n_results": n_results, "where": where})
        if where is not None and not self.support_where:
            raise ValueError("이 엔진은 where 를 지원하지 않습니다")
        rows = self.rows
        if where is not None:
            rows = [r for r in rows if _meta_matches(r[1], where)]
        rows = rows[:n_results]
        return {"documents": [[r[0] for r in rows]],
                "metadatas": [[r[1] for r in rows]],
                "distances": [[r[2] for r in rows]]}

    def add(self, documents=None, metadatas=None, ids=None):
        self.added.append({"documents": documents, "metadatas": metadatas, "ids": ids})


def _kb(rows, support_where=True):
    """무거운 `__init__`(임베딩 모델 로딩)을 건너뛰고 컬렉션만 갈아끼운다."""
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb.collection = _FakeCollection(rows, support_where=support_where)
    return kb


_ROWS = [
    ("품질 산출물", {"owner_dept_id": "quality", "project_id": "Q1"}, 0.1),
    ("영업 산출물", {"owner_dept_id": "sales", "project_id": "S1"}, 0.2),
    ("전사 산출물", {"owner_dept_id": "hq", "project_id": "H1"}, 0.3),
    ("레거시 산출물", {"owner_dept_id": "", "project_id": "L1"}, 0.4),
]


def test_search_without_where_does_not_pass_filter():
    kb = _kb(_ROWS)
    out = kb.search_similar("q", n_results=4)
    assert kb.collection.calls[0]["where"] is None
    assert len(out) == 4
    assert out[0]["distance"] == 0.1, "거리가 실려와야 호출부가 관련성을 판단할 수 있다"


def test_search_with_where_delegates_to_engine():
    kb = _kb(_ROWS)
    out = kb.search_similar("q", n_results=4, where={"owner_dept_id": {"$in": ["quality"]}})
    assert kb.collection.calls[0]["where"] == {"owner_dept_id": {"$in": ["quality"]}}
    assert [s["metadata"]["project_id"] for s in out] == ["Q1"]


def test_search_where_fallback_overfetches_and_filters_in_python():
    """★ 엔진이 `$in` 을 못 받아도 필터를 포기하지 않는다."""
    kb = _kb(_ROWS, support_where=False)
    out = kb.search_similar("q", n_results=2, where={"owner_dept_id": {"$in": ["quality", "hq"]}})
    assert len(kb.collection.calls) == 2, "1차 시도 실패 → over-fetch 재시도"
    assert kb.collection.calls[1]["n_results"] == 10, "n_results*5 로 넉넉히 조회"
    assert kb.collection.calls[1]["where"] is None, "폴백은 엔진에 where 를 넘기지 않는다"
    assert [s["metadata"]["project_id"] for s in out] == ["Q1", "H1"]


def test_search_where_fallback_truncates_to_requested_count():
    kb = _kb(_ROWS, support_where=False)
    out = kb.search_similar("q", n_results=1, where={"owner_dept_id": {"$in": ["quality", "hq"]}})
    assert len(out) == 1, "over-fetch 한 만큼을 그대로 돌려주면 프롬프트가 부풀어난다"


def test_search_no_collection_is_safe():
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb.collection = None
    assert kb.search_similar("q") == []


# ── ③ `get_relevant_context` 3중 방어 ─────────────────────────────────────
class _State:
    def __init__(self, dept="", name="P", idea="아이디어"):
        self.owner_dept_id = dept
        self.project_name = name
        self.initial_idea = idea


@pytest.fixture
def _dept_tree(monkeypatch):
    """`quality` 의 조상 체인이 `hq/quality/` 인 조직을 흉내낸다."""
    import core.org_directory as od

    class _Stub:
        def get_department(self, dept_id):
            return {"quality": {"path": "hq/quality/"},
                    "sales": {"path": "hq/sales/"}}.get(dept_id)

    monkeypatch.setattr(od, "org_directory", _Stub())


def test_killswitch_returns_nothing(monkeypatch):
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", False)
    kb = _kb(_ROWS)
    assert kb.get_relevant_context(_State(dept="quality")) == ""
    assert kb.collection.calls == [], "킬스위치가 켜지면 검색 자체를 하지 않는다"


def test_dept_chain_filter_is_self_plus_ancestors(monkeypatch, _dept_tree):
    """프롬프트 주입은 자기+조상만 — 형제 부서(sales)가 섞이면 횡방향 유출이다."""
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    kb = _kb(_ROWS)
    ctx = kb.get_relevant_context(_State(dept="quality"))
    assert kb.collection.calls[0]["where"] == {"owner_dept_id": {"$in": ["hq", "quality"]}}
    assert "품질 산출물" in ctx and "전사 산출물" in ctx
    assert "영업 산출물" not in ctx, "형제 부서 산출물이 프롬프트에 들어가면 안 된다"
    assert "레거시 산출물" not in ctx, "미태깅 청크는 배제(fail-closed)"


def test_dept_lookup_failure_falls_back_to_self_only(monkeypatch):
    """조직 조회가 죽어도 필터를 포기하지 않는다(자기 부서로 축소)."""
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    import core.org_directory as od

    class _Broken:
        def get_department(self, dept_id):
            raise RuntimeError("no such table")

    monkeypatch.setattr(od, "org_directory", _Broken())
    kb = _kb(_ROWS)
    kb.get_relevant_context(_State(dept="quality"))
    assert kb.collection.calls[0]["where"] == {"owner_dept_id": {"$in": ["quality"]}}


def test_untagged_project_is_fail_open_by_design(monkeypatch):
    """의도적 비대칭 — 여기서 fail-closed 로 가면 마이그레이션 전 레거시가 전부 굶는다.
    그 구멍은 생성 시점 소유권 기록으로 막는다(아래 create_project 테스트)."""
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    kb = _kb(_ROWS)
    kb.get_relevant_context(_State(dept=""))
    assert kb.collection.calls[0]["where"] is None


def test_distance_cutoff_drops_irrelevant(monkeypatch, _dept_tree):
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    monkeypatch.setattr(config, "RAG_PAST_CASES_CUTOFF", 0.15)
    kb = _kb(_ROWS)
    ctx = kb.get_relevant_context(_State(dept="quality"))
    assert "품질 산출물" in ctx
    assert "전사 산출물" not in ctx, "임계값(0.15) 초과는 무관한 문서로 본다"


def test_all_irrelevant_returns_empty_string(monkeypatch, _dept_tree):
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    monkeypatch.setattr(config, "RAG_PAST_CASES_CUTOFF", 0.001)
    kb = _kb(_ROWS)
    assert kb.get_relevant_context(_State(dept="quality")) == ""


def test_self_release_is_excluded(monkeypatch, _dept_tree):
    """자기 자신의 과거 릴리스는 '참고 사례'가 아니다(자기 참조로 컨텍스트만 부푼다)."""
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    monkeypatch.setattr(config, "RAG_PAST_CASES_CUTOFF", 0.65)
    kb = _kb(_ROWS)
    ctx = kb.get_relevant_context(_State(dept="quality", name="Q1"))
    assert "품질 산출물" not in ctx
    assert "전사 산출물" in ctx


def test_injection_capped_at_three(monkeypatch):
    monkeypatch.setattr(config, "RAG_PAST_CASES_ENABLED", True)
    monkeypatch.setattr(config, "RAG_PAST_CASES_CUTOFF", 0.65)
    rows = [(f"문서{i}", {"owner_dept_id": "", "project_id": f"P{i}"}, 0.1) for i in range(6)]
    kb = _kb(rows)
    ctx = kb.get_relevant_context(_State(dept=""))
    assert ctx.count("--- [과거 사례") == 3, "상한 3건 — 프롬프트 예산을 지킨다"


def test_empty_query_returns_nothing():
    kb = _kb(_ROWS)
    assert kb.get_relevant_context(_State(dept="quality", name="", idea="")) == ""


# ── ④ 배선: 인덱싱 메타에 `owner_dept_id` 가 실리는가 ─────────────────────
def test_index_release_stamps_owner_dept_from_metadata():
    kb = _kb([])
    kb.index_release("P1", "R1", {"prd.md": "본문"}, {"owner_dept_id": "quality"})
    metas = kb.collection.added[0]["metadatas"]
    assert metas and all(m["owner_dept_id"] == "quality" for m in metas)


def test_index_release_without_dept_is_untagged():
    kb = _kb([])
    kb.index_release("P1", "R1", {"prd.md": "본문"}, {"template_id": "default"})
    assert kb.collection.added[0]["metadatas"][0]["owner_dept_id"] == ""


# ── ④-b 배선: 게시 라우트가 소유 부서를 넘기는가 (★ 회귀 방지) ────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # ./projects, ./library 가 tmp 아래에 생기도록
    app = FastAPI()
    app.include_router(fc.router)
    return app, TestClient(app)


def _as(app, user_id="bob", dept="quality", **kw):
    """요청자를 특정 부서 소속으로 고정한다."""
    scope = AccessScope(user_id=user_id, primary_dept_id=dept, unrestricted=False,
                        readable_dept_ids=frozenset({dept}),
                        writable_dept_ids=frozenset({dept}), **kw)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def test_create_project_stamps_creator_dept(client):
    """★ 소유권이 안 찍히면 프롬프트 주입 필터가 아예 걸리지 않는다(fail-open)."""
    app, c = client
    _as(app, user_id="bob", dept="quality")
    r = c.post("/api/v1/factory/projects", json={"project_id": "P1"})
    assert r.status_code == 200, r.text
    own = fc._read_project_ownership("./projects/P1")
    assert own["owner_dept_id"] == "quality"
    assert own["owner_user_id"] == "bob"


def test_create_project_without_dept_stays_untagged(client):
    """조직 미도입/무소속 — 종전과 동일하게 미태깅(하위호환)."""
    app, c = client
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="", scope=AccessScope(unrestricted=True))
    r = c.post("/api/v1/factory/projects", json={"project_id": "P2"})
    assert r.status_code == 200, r.text
    assert fc._read_project_ownership("./projects/P2")["owner_dept_id"] == ""


def test_mega_sub_projects_own_their_domain_dept(client):
    """서브 프로젝트의 `domain` 이 곧 `dept_id` — 마이그레이션 규약과 같은 값."""
    app, c = client
    _as(app, user_id="bob", dept="quality")
    r = c.post("/api/v1/factory/projects/mega", json={"mega_project_id": "MEGA"})
    assert r.status_code == 200, r.text
    subs = r.json()["sub_projects"]
    assert subs, "서브 프로젝트가 생성되어야 한다"
    for domain, sub_id in subs.items():
        assert fc._read_project_ownership(f"./projects/{sub_id}")["owner_dept_id"] == domain
    master = fc._read_project_ownership("./projects/MEGA")
    assert master["owner_dept_id"] == "hq" and master["visibility"] == "company"


def test_release_passes_owner_dept_to_indexing(client, monkeypatch):
    """★★ 이 배선이 빠져 있었다 — 청크가 전부 미태깅으로 들어가 RAG 가 조용히 0건이 됐다."""
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P3"}).status_code == 200
    with open("./projects/P3/latest_state.json", "w", encoding="utf-8") as f:
        json.dump({"project_name": "P3", "template_id": "default",
                   "prd_summary": "요구사항 본문"}, f)

    seen = {}
    done = threading.Event()

    def _capture(project_id, release_id, files_content, metadata):
        seen.update({"project_id": project_id, "metadata": metadata})
        done.set()

    from core.knowledge_base import knowledge_base
    monkeypatch.setattr(knowledge_base, "index_release", _capture)

    r = c.post("/api/v1/factory/P3/release")
    assert r.status_code == 200, r.text
    assert done.wait(10), "인덱싱이 트리거되지 않았다"
    assert seen["metadata"]["owner_dept_id"] == "quality"


def test_release_json_records_ownership_at_publish_time(client):
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P4"}).status_code == 200
    with open("./projects/P4/latest_state.json", "w", encoding="utf-8") as f:
        json.dump({"project_name": "P4", "template_id": "default"}, f)

    r = c.post("/api/v1/factory/P4/release")
    assert r.status_code == 200, r.text
    rid = r.json()["release_id"]
    with open(os.path.join("library", rid, "release.json"), encoding="utf-8") as f:
        rel = json.load(f)
    assert rel["owner_dept_id"] == "quality"
    assert rel["visibility"] == "dept"


# ── ③-b 지식팩 연결 시점 차단 ─────────────────────────────────────────────
def _fake_packs(monkeypatch, packs):
    from core.knowledge_base import knowledge_base
    monkeypatch.setattr(knowledge_base, "list_packs", lambda: packs)


def test_linking_unreadable_pack_is_denied(client, monkeypatch):
    """★ 읽을 권한 없는 팩을 연결하면 그 뒤 모든 프롬프트가 합법적으로 그 팩을 참조한다."""
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P5"}).status_code == 200
    _fake_packs(monkeypatch, [{"pack_id": "fin_pack", "owner_dept_id": "finance"}])

    r = c.put("/api/v1/factory/projects/P5/knowledge", json={"knowledge_pack_ids": ["fin_pack"]})
    assert r.status_code == 403, r.text


def test_linking_own_dept_pack_is_allowed(client, monkeypatch):
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P6"}).status_code == 200
    _fake_packs(monkeypatch, [{"pack_id": "q_pack", "owner_dept_id": "quality"}])

    r = c.put("/api/v1/factory/projects/P6/knowledge", json={"knowledge_pack_ids": ["q_pack"]})
    assert r.status_code == 200, r.text
    assert fc._read_project_packs("./projects/P6") == ["q_pack"]


def test_linking_unowned_pack_is_allowed_for_compatibility(client, monkeypatch):
    """소유 부서 미기록 팩은 전사 공유로 본다 — Phase 3 과 같은 규약(하위호환)."""
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P7"}).status_code == 200
    _fake_packs(monkeypatch, [{"pack_id": "legacy_pack"}])

    r = c.put("/api/v1/factory/projects/P7/knowledge", json={"knowledge_pack_ids": ["legacy_pack"]})
    assert r.status_code == 200, r.text


def test_unknown_pack_still_404(client, monkeypatch):
    app, c = client
    _as(app, user_id="bob", dept="quality")
    assert c.post("/api/v1/factory/projects", json={"project_id": "P8"}).status_code == 200
    _fake_packs(monkeypatch, [{"pack_id": "q_pack", "owner_dept_id": "quality"}])

    r = c.put("/api/v1/factory/projects/P8/knowledge", json={"knowledge_pack_ids": ["ghost"]})
    assert r.status_code == 404, r.text


# ══════════════════════════════════════════════════════════════════════════
# [2026-07-30] 지식팩 검색의 조직 범위 필터 — 색인에 심은 범위를 검색이 쓰는가
# ══════════════════════════════════════════════════════════════════════════
def _pack_kb(rows, monkeypatch, pack_id="p1"):
    """`search_packs` 용 대역 — 팩 존재 판정과 컬렉션만 갈아끼운다."""
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb.client = object()
    col = _FakeCollection(rows)
    monkeypatch.setattr(KnowledgeBase, "_manifest_path", lambda self, pid: __file__)
    monkeypatch.setattr(KnowledgeBase, "_pack_collection", lambda self, pid: col)
    return kb, col


# ⚠️ `search_packs` 는 팩당 `min(3, n_total)` 건만 가져온다. 그래서 필터를 검증할 행은
#   **상위 3건 안에** 있어야 한다 — 거리로 이미 탈락한 행이 "필터가 막았다"로 보이면 그 테스트는
#   아무것도 증명하지 않는다(허수 통과).
_PACK_ROWS = [
    ("전사 표준 문서", {"owner_org_id": "LS_MNM", "filename": "std.docx"}, 0.1),
    ("동제련 전용 문서", {"owner_org_id": "MNM_COPPER", "filename": "cu.docx"}, 0.2),
    ("예전 업로드", {"filename": "legacy.docx"}, 0.3),          # owner_org_id 없음
]


def test_search_packs_without_scope_returns_everything(monkeypatch):
    """★ 범위를 주지 않으면 필터하지 않는다 — 종전 동작(ECM 미도입 흐름)을 깨지 않는다."""
    kb, col = _pack_kb(_PACK_ROWS, monkeypatch)
    assert len(kb.search_packs(["p1"], "질의", n_total=10)) == 3
    assert col.calls[0]["n_results"] == 3, "팩당 상한(3)이 바뀌면 아래 필터 테스트도 함께 봐야 한다"


def test_search_packs_filters_by_org_scope(monkeypatch):
    """★★ 색인할 때 범위를 심어 두고 검색에서 쓰지 않으면 그 메타데이터는 장식이다.

    등록부에서 `owner_org_id` 로 통제한 문서가 색인되는 순간 통제 밖으로 나가면 안 된다.
    세 행 모두 상위 3건에 들어오므로, 빠지는 것은 **필터가 막은 것**이다."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes", lambda node: {"MNM_BATTERY", "LS_MNM"})
    kb, _ = _pack_kb(_PACK_ROWS, monkeypatch)

    got = [h["content"] for h in
           kb.search_packs(["p1"], "질의", n_total=10, scope_node_id="MNM_BATTERY")]
    assert got == ["전사 표준 문서"], f"범위 필터가 정확하지 않다: {got}"
    # → 상속된 전사 문서는 통과, 형제 조직(MNM_COPPER)과 범위 미기재는 제외(fail-closed)


def test_search_packs_fails_closed_when_scope_cannot_be_resolved(monkeypatch):
    """★★ 범위 해석 실패를 '전부 보임'으로 처리하면 리솔버 장애가 곧 전사 유출이 된다."""
    import core.enterprise_context.scoping as sc

    def _boom(node):
        raise RuntimeError("resolver down")
    monkeypatch.setattr(sc, "visible_scopes", _boom)
    kb, _ = _pack_kb(_PACK_ROWS, monkeypatch)

    assert kb.search_packs(["p1"], "질의", scope_node_id="MNM_BATTERY") == []
