"""WBS 태스크의 산출물 종류 — 「이 태스크가 계약 대상인가」를 답하는 **한 곳**.

설계서 [I-4 §15] 는 이 판정을 두 번 고쳐 썼다. rev.2 는 「데이터 CRUD 를 포함한다고
판정된 태스크」만 계약을 요구했는데, 그것은 **순환 논리**였다 — 데이터 사용을 놓친
태스크가 곧 계약을 우회하는 태스크가 된다. 그리고 놓치는 쪽은 언제나 「간단해 보이는」
앱이다. 그래서 기준을 **산출물의 종류**로 옮겼다.

| `artifact_kind` | 계약 |
|---|---|
| `APP`       | **필수** |
| `SIMULATOR` | **필수** |
| `REPORT`    | 불필요 |
| `DOCUMENT`  | 불필요 |
| `LIBRARY`   | 불필요 |

★★★ **판독할 수 없으면 계약 대상으로 처리한다.** 값이 없든, 목록 밖이든, 타입이
  틀렸든 결과는 같다 — `APP`. 「모르면 면제」는 규칙이 아니라 우회로다.
  ⚠️ 이 판정을 LLM 출력에 맡기는 순간 계약은 **가장 필요한 앱에서** 빠진다.
    WBS 는 LLM 이 쓴다. 그 LLM 이 `artifact_kind` 를 빼먹거나 `"app"` 대신
    `"application"` 이라고 쓰면, 관대한 파서는 그것을 「분류 불가 → 면제」로 읽는다.

★ 데이터가 없는 앱도 **「데이터셋 0개인 계약」**을 갖는다. 0개라는 선언 자체가 통제다 —
  나중에 하나가 생기면 지문이 바뀌고 게이트가 열린다.

⚠️⚠️ **이 모듈은 아무것도 import 하지 않는다.** [I-4 2.2a] 에서 같은 규칙을 두 계층이
  각자 구현했다가 세 조합에서 답이 갈렸다. 판정이 한 곳에만 있어야 갈라질 수 없다.
"""
from typing import Any, Dict, List, Tuple

#: 닫힌 목록. 여기 없는 값은 **값이 없는 것과 똑같이** 다룬다.
APP = "APP"
SIMULATOR = "SIMULATOR"
REPORT = "REPORT"
DOCUMENT = "DOCUMENT"
LIBRARY = "LIBRARY"

ARTIFACT_KINDS: Tuple[str, ...] = (APP, SIMULATOR, REPORT, DOCUMENT, LIBRARY)

#: 계약이 **필수**인 종류. 사용자가 실행할 수 있는 App-in-App SW 릴리스를 만드는 것들이다.
CONTRACT_REQUIRED_KINDS: Tuple[str, ...] = (APP, SIMULATOR)

#: 판독 실패 시 떨어지는 자리. fail-closed 이므로 **계약 필수 쪽**이어야 한다.
UNREADABLE_FALLBACK = APP

#: 어떻게 정해진 값인가. 감사자는 「기획이 APP 이라고 말했다」와 「읽을 수 없어 APP 으로
#: 떨어뜨렸다」를 구분할 수 있어야 한다 — 후자가 많으면 그것은 기획 프롬프트의 결함이다.
SOURCE_DECLARED = "declared"
SOURCE_FALLBACK = "fallback"

#: 계약을 만들 책임자. 계약 대상 태스크에는 **반드시** 들어간다.
TECH_LEAD = "Tech_Lead"

#: 태스크에 기록하는 키 이름(호출부가 문자열을 반복하지 않게 한다).
KIND_KEY = "artifact_kind"
SOURCE_KEY = "artifact_kind_source"

#: ── 적용 범위(opt-in) ────────────────────────────────────────────────────
#: [I-4 §3 「기존 프로젝트에 끼워 넣지 않는다」] 계약 절차는 **신규 워크플로우부터**
#: 적용한다. 진행 중 프로젝트에 노드를 삽입하면 `completed_agents` 순서 전제와
#: 체크포인터 상태가 어긋나고, 그 결함은 **재개할 때에야** 드러난다.
PROFILE_NONE = ""
PROFILE_V1 = "v1"
PROFILE_KEY = "runtime_contract_profile"

RUNTIME_CONTRACT_PROFILES: Tuple[str, ...] = (PROFILE_NONE, PROFILE_V1)


def profile_enforces_contract(profile: Any) -> bool:
    """이 프로필이 계약 절차를 강제하는가.

    ⚠️⚠️ **여기만 fail-closed 가 아니다.** 판독할 수 없는 프로필은 「강제하지 않음」
      으로 떨어진다 — `artifact_kind` 와 정반대다. 이유를 적어 둔다:

      · `artifact_kind` 의 판독 실패는 **새로 만드는 앱** 하나가 계약을 건너뛰는 일이다.
      · 프로필의 판독 실패를 강제 쪽으로 떨어뜨리면 **이미 돌고 있는 모든 프로젝트**가
        소급해서 새 절차를 타고, 재개하는 순간 체크포인터가 어긋난다.

      즉 두 판정은 「모르면 어느 쪽이 덜 위험한가」가 서로 반대다. 그래서 이 비대칭은
      실수가 아니라 **선택**이고, 대신 신규 생성 경로가 `v1` 을 **명시**할 책임을 진다
      (`_write_project_meta`). 기본값이 조용히 `v1` 이 되는 경로가 하나라도 생기면
      위 위험이 그대로 돌아오므로, 그 경계는 회귀로 고정한다."""
    return isinstance(profile, str) and profile.strip().lower() == PROFILE_V1


def normalize_kind(raw: Any) -> Tuple[str, str]:
    """`(종류, 출처)` 를 돌려준다. **예외를 올리지 않는다** — 판독 실패도 답이다.

    대소문자와 앞뒤 공백은 흡수한다(`"app"`, `" App "` → `APP`). 그 이상은 추측하지
    않는다 — `"application"` 을 `APP` 으로 읽어 주기 시작하면 목록이 닫혀 있지 않은
    것과 같아지고, 어디까지 읽어 주는지를 아무도 모르게 된다.
    ⚠️ 관대해져서 잃는 것은 없어 보이지만, 잃는 것은 **「목록에 없다」는 신호**다.
    """
    if isinstance(raw, str):
        candidate = raw.strip().upper()
        if candidate in ARTIFACT_KINDS:
            return candidate, SOURCE_DECLARED
    return UNREADABLE_FALLBACK, SOURCE_FALLBACK


def requires_contract(kind: Any) -> bool:
    """이 종류가 App Runtime Contract 를 요구하는가.

    ⚠️ 정규화를 거치므로 **판독 불가 값은 True 가 된다.** 호출부가 미리 정규화했는지
      여부와 무관하게 같은 답이 나와야 한다 — 두 경로가 다른 답을 내면 그것이 곧
      우회로다."""
    normalized, _ = normalize_kind(kind)
    return normalized in CONTRACT_REQUIRED_KINDS


def task_requires_contract(task: Any) -> bool:
    """WBS 태스크 하나가 계약 대상인가.

    ⚠️ 태스크가 dict 가 아니면 **계약 대상으로 본다.** 읽을 수 없는 태스크를 통과시키는
      것은 판독 불가 종류를 통과시키는 것과 같다."""
    if not isinstance(task, dict):
        return True
    return requires_contract(task.get(KIND_KEY))


def normalize_task(task: Any) -> Dict[str, Any]:
    """태스크 하나를 정규화한 **새 dict** 로 돌려준다.

    · `artifact_kind` 를 닫힌 목록 값으로 확정하고 `artifact_kind_source` 를 남긴다.
    · 계약 대상이면 `required_agents` 에 `Tech_Lead` 를 **넣는다**(중복은 만들지 않고,
      기존 순서는 보존한다 — 순서가 실행 순서를 뜻하는 자리가 있다).

    ⚠️ 원본을 그대로 바꾸지 않는다. 호출부가 같은 리스트를 다른 곳에서도 들고 있을 수
      있고, 그때 조용히 바뀌면 원인을 찾기 어렵다."""
    if not isinstance(task, dict):
        #: 읽을 수 없는 태스크도 **버리지 않는다.** 버리면 WBS 개수가 조용히 줄고,
        #: 그 손실은 실행이 끝난 뒤에야 드러난다.
        return {KIND_KEY: UNREADABLE_FALLBACK, SOURCE_KEY: SOURCE_FALLBACK,
                "required_agents": [TECH_LEAD], "malformed_task": repr(task)[:200]}

    out = dict(task)
    kind, source = normalize_kind(task.get(KIND_KEY))
    out[KIND_KEY] = kind
    out[SOURCE_KEY] = source

    if kind in CONTRACT_REQUIRED_KINDS:
        agents = task.get("required_agents")
        agents = [a for a in agents if isinstance(a, str)] if isinstance(agents, list) else []
        if TECH_LEAD not in agents:
            #: 맨 앞에 둔다 — 계약이 나오기 전에는 Backend·Frontend 가 만들 것이 없다.
            agents = [TECH_LEAD] + agents
        out["required_agents"] = agents
    return out


def normalize_tasks(tasks: Any) -> List[Dict[str, Any]]:
    """WBS 태스크 목록 전체를 정규화한다.

    ★★★ **목록이 아니면 빈 목록이 아니라 「판독 불가 태스크 한 건」이다.**

    ⚠️ 빈 목록을 돌려주면 계약 대상이 0건이 되고, 그러면 게이트 판정이
      `NOT_APPLICABLE` 로 떨어져 **WBS 를 통째로 읽지 못한 프로젝트가 계약 없이
      통과한다.** 태스크 하나를 못 읽는 것보다 WBS 전체를 못 읽는 것이 더 나쁜데,
      더 나쁜 쪽이 더 관대하게 처리되고 있었다 — 그 방향이 뒤집혀 있으면 공격자든
      버그든 **WBS 를 깨뜨리는 것**이 가장 쉬운 우회로가 된다."""
    if not isinstance(tasks, list):
        return [normalize_task(tasks)]
    return [normalize_task(t) for t in tasks]


def contract_required_task_ids(tasks: Any) -> List[str]:
    """계약이 필요한 태스크의 `task_id` 목록. 게이트가 「무엇이 남았나」를 셀 때 쓴다."""
    return [str(t.get("task_id", "")) for t in normalize_tasks(tasks)
            if t.get(KIND_KEY) in CONTRACT_REQUIRED_KINDS]
