"""체크포인트 직렬화 허용목록 — **재개 가능성을 지키는 한 줄짜리 계약.**

## 이 파일이 없으면 무슨 일이 생기나 (2026-07-29 실측)

langgraph 는 체크포인트를 msgpack 으로 저장하면서, 우리 커스텀 타입(`state_models.*`)을
**허용목록에 없으면 원래 타입으로 복원하지 않는다**. 지금은 기본이 permissive(경고만)라
동작하지만, `LANGGRAPH_STRICT_MSGPACK=true` 를 켜거나 상류가 strict 를 기본값으로 바꾸면:

    Blocked deserialization of state_models.ProjectState - not in allowed_msgpack_modules
    → `ProjectState` 가 **plain dict 로 강등**된다(예외 없음, 경고 한 줄).

⚠️ **값이 사라지는 게 아니라 접근 방법이 어긋나는 것**이 이 결함의 진짜 성질이다. dict 안에
  값은 그대로 있는데, 이 코드베이스는 상태를 `getattr(state, "x", "")` 로 널리 읽는다.
  dict 에 `getattr` 을 하면 **조용히 기본값**이 나온다. 실측(2026-07-29):

    getattr(restored, "current_sprint_task_id", "")  → ''   (실제 값은 'WBS-001')
    getattr(restored, "enterprise_scope_id", "")     → ''   (실제 값은 'BATTERY')

  두 번째 줄이 특히 위험하다 — 조직 범위가 빈 문자열이면 **범위 필터가 통째로 꺼진다**
  (`scoping` 규칙 3: 범위 미지정이면 필터하지 않는다). 즉 이 결함 하나가 D-016 으로 막은
  기준정보·MCP 실측값의 조직 격리를 **조용히 되돌린다**. 터지지 않으므로 아무도 모른다.

## 그래서 여기서 하는 일

상태에 실릴 수 있는 우리 타입을 **명시적으로 등록**한다. 등록은 타입 객체로 한다 —
문자열 `("state_models", "ProjectState")` 로 적으면 클래스를 옮기거나 이름을 바꿨을 때
목록만 조용히 낡는다(다시 같은 사고). 타입으로 적으면 import 가 깨져서 즉시 드러난다.

**상태 모델에 새 BaseModel/Enum 을 추가하면 여기에도 추가해야 한다.**
`tests/test_checkpoint_serde.py` 가 state_models 의 모델 목록과 이 목록을 대조해
빠뜨림을 잡는다 — 사람의 기억에 의존하지 않는다.
"""
from typing import Any, List

import state_models


def state_model_types() -> List[type]:
    """`state_models` 의 pydantic 모델 전부(체크포인트에 실릴 수 있는 타입).

    하드코딩한 목록이 아니라 **모듈에서 수집**한다 — 새 모델이 늘어나도 자동으로 따라간다.
    (테스트는 이 함수가 아니라 모듈을 다시 훑어 교차 검증한다.)"""
    from pydantic import BaseModel

    out = []
    for name in dir(state_models):
        obj = getattr(state_models, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            # 다른 모듈에서 import 해 온 것은 그쪽 소유다(중복 등록 방지).
            if obj.__module__ == state_models.__name__:
                out.append(obj)
    return out


def build_serializer() -> Any:
    """허용목록을 실은 직렬화기. langgraph 가 없거나 옵션을 모르면 **None** 을 돌려준다.

    ⚠️ None 은 "기본 직렬화기를 쓰라"는 뜻이다 — 여기서 예외를 던지면 상류 버전이 바뀌었을 때
      서버가 아예 기동하지 못한다. 계측·보호 장치가 본체를 죽이면 안 된다."""
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except Exception as e:      # pragma: no cover - 상류 구조 변경 시
        print(f"⚠️ [Checkpointer] 직렬화기 허용목록 적용 생략(langgraph 구조 변경?): {e}")
        return None
    try:
        return JsonPlusSerializer(allowed_msgpack_modules=tuple(state_model_types()))
    except TypeError as e:      # pragma: no cover - 옵션명이 바뀐 경우
        print(f"⚠️ [Checkpointer] allowed_msgpack_modules 미지원 — 기본 직렬화기 사용: {e}")
        return None
