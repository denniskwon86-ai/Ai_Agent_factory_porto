"""체크포인트 복원 가능성 — **strict 직렬화에서 상태가 제 타입으로 돌아오는가.**

## 왜 이 테스트가 필요한가 (2026-07-29 실측)

허용목록에 없는 커스텀 타입은 **plain dict 로 강등**된다(예외 없음, 경고 한 줄).
값은 dict 안에 남아 있지만 이 코드베이스는 상태를 `getattr(state, "x", "")` 로 널리 읽고,
dict 에 `getattr` 을 하면 **조용히 기본값**이 나온다. 실측:

    getattr(restored, "enterprise_scope_id", "") → ''   (실제 값은 'BATTERY')

조직 범위가 빈 문자열이면 범위 필터가 통째로 꺼진다 — 즉 이 결함 하나가 D-016 으로 막은
조직 격리를 **조용히 되돌린다**. 터지지 않으므로 아무도 모른다.

그래서 여기서 strict 를 **직접 켜고** 왕복을 확인한다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.checkpoint_serde import build_serializer, state_model_types
from state_models import ProjectState


def _strict_serializer():
    """strict 모드를 켠 상태의 직렬화기(허용목록 적용본)."""
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    import importlib

    import langgraph.checkpoint.serde.jsonplus as jp
    import langgraph.checkpoint.serde._msgpack as lgm
    importlib.reload(lgm)
    importlib.reload(jp)
    return jp.JsonPlusSerializer(allowed_msgpack_modules=tuple(state_model_types()))


@pytest.fixture()
def strict(monkeypatch):
    saved = os.environ.get("LANGGRAPH_STRICT_MSGPACK")
    ser = _strict_serializer()
    yield ser
    # 전역 모듈 상태를 원복한다 — 안 하면 뒤 테스트가 strict 로 오염된다.
    if saved is None:
        os.environ.pop("LANGGRAPH_STRICT_MSGPACK", None)
    else:
        os.environ["LANGGRAPH_STRICT_MSGPACK"] = saved
    import importlib

    import langgraph.checkpoint.serde._msgpack as lgm
    import langgraph.checkpoint.serde.jsonplus as jp
    importlib.reload(lgm)
    importlib.reload(jp)


def _sample_state() -> ProjectState:
    return ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": "./projects/p1",
        "current_sprint_task_id": "WBS-001",
        "file_index": {"src/App.tsx": {"path": "src/App.tsx", "purpose": "메인 화면"}},
        "enterprise_scope_id": "BATTERY",
        "human_feedback_queue": [{"task_id": "WBS-001", "feedback": "단가 근거", "status": "pending"}],
    })


def test_state_survives_strict_roundtrip(strict):
    """★★ 이 파일의 본론 — strict 에서도 상태가 그대로 돌아온다."""
    payload = {"state": _sample_state()}
    restored = strict.loads_typed(strict.dumps_typed(payload))

    assert "state" in restored, "상태 키가 사라졌다 — 허용목록 누락(조용한 소실)"
    st = restored["state"]
    assert isinstance(st, ProjectState)
    assert st.current_sprint_task_id == "WBS-001"
    # 중첩 커스텀 타입(FileMetadata)까지 복원돼야 한다 — 여기가 원래 경고가 나던 지점이다.
    assert st.file_index["src/App.tsx"].purpose == "메인 화면"
    # ★ 조직 범위가 getattr 로 읽힌다 = D-016 범위 필터가 재개 후에도 살아 있다.
    assert getattr(st, "enterprise_scope_id", "") == "BATTERY"


def test_without_allowlist_getattr_silently_returns_defaults(strict):
    """★★ 대조군 — 허용목록이 없을 때 **정확히 무엇이 위험한지**를 눈으로 남긴다.

    값이 사라지는 게 아니라 dict 로 강등되고, `getattr` 접근이 조용히 기본값을 준다.
    특히 `enterprise_scope_id` 가 '' 가 되면 조직 범위 필터가 꺼진다(D-016 무력화).
    이 테스트가 실패하면 상류가 동작을 바꾼 것이므로 대책의 전제도 다시 봐야 한다."""
    import langgraph.checkpoint.serde.jsonplus as jp

    bare = jp.JsonPlusSerializer()          # strict + 허용목록 없음
    restored = bare.loads_typed(bare.dumps_typed({"state": _sample_state()}))["state"]

    assert isinstance(restored, dict), "상류 동작이 바뀌었다 — 허용목록 정책을 재검토할 것"
    assert restored["enterprise_scope_id"] == "BATTERY"          # 값은 남아 있는데
    assert getattr(restored, "enterprise_scope_id", "") == ""    # 읽는 쪽에서 사라진다
    assert getattr(restored, "current_sprint_task_id", "") == ""


def test_allowlist_covers_every_state_model():
    """★ 새 상태 모델을 추가하고 등록을 잊는 것을 막는다(사람 기억에 의존하지 않는다)."""
    from pydantic import BaseModel

    import state_models

    declared = {
        obj for name in dir(state_models)
        if isinstance(obj := getattr(state_models, name), type)
        and issubclass(obj, BaseModel) and obj is not BaseModel
        and obj.__module__ == state_models.__name__
    }
    assert declared, "state_models 에서 모델을 하나도 못 찾았다 — 수집 로직이 깨졌다"
    assert declared == set(state_model_types())


def test_builder_never_breaks_startup(monkeypatch):
    """★ 보호 장치가 본체를 죽이면 안 된다 — 상류 구조가 바뀌면 None 을 돌려주고 계속 간다."""
    import core.checkpoint_serde as cs

    def _boom(*a, **k):
        raise TypeError("allowed_msgpack_modules 라는 인자를 모른다")

    import langgraph.checkpoint.serde.jsonplus as jp
    monkeypatch.setattr(jp, "JsonPlusSerializer", _boom)
    assert cs.build_serializer() is None


def test_runtime_saver_uses_the_allowlist():
    """★★ 배선 확인 — 만들어만 두고 체크포인터에 안 걸면 아무 효과가 없다."""
    import inspect

    import core.agent_graph as ag

    src = inspect.getsource(ag._get_runtime_saver)
    assert "build_serializer" in src, "런타임 체크포인터가 허용목록을 쓰지 않는다"
    assert "serde=_serde" in src, "saver 에 serde 를 전달하지 않는다"
    assert "build_serializer" in inspect.getsource(ag._build_workflow) or \
        "build_serializer" in inspect.getsource(ag.create_factory_graph), \
        "휘발성(MemorySaver) 경로에도 같은 규칙이 걸려 있어야 한다"
