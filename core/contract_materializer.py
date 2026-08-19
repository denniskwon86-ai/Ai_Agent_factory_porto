"""[Wave F-0] 승인된 계약 → 실제 데이터셋과 결속. **승인이 무언가를 만들게 한다.**

## 왜 이 파일이 뒤늦게 생겼나

I-4 는 계약을 «쓰고 · 합산하고 · 검토하고 · 승인하고 · 봉인하는» 길을 다 만들었다.
그런데 승인 뒤에 **실제로 데이터셋을 만드는 단계가 운영 코드에 없었다** — 승인 후
하는 일은 타입 어댑터 파일을 쓰는 것 하나뿐이었다(`nodes/contract.py`).

⚠️ 그래서 지금까지 계약 경로를 지난 릴리스가 **하나도 없다**(운영 `app_data.db` 에
  결속 표가 아예 없다). 「승인은 되는데 아무것도 생기지 않는」 상태였고, 그 상태는
  오류를 내지 않았다. 봉인은 「그때와 같은가」에 답할 뿐 「무언가 생겼는가」에는
  답하지 않기 때문이다.

## 이 파일이 지키는 것 넷

★★★ ① **부분 물질화를 남기지 않는다.** 데이터셋 다섯 중 셋만 만들어지면 앱은 두 개를
  「없는 것」으로 보고 화면에서 지운다. 하나라도 못 만들면 **아무것도 만들지 않는다.**

★★★ ② **사내 원천은 «어느 조직의 어느 판인지» 를 못 박는다.** 계약은 「구매주문에서
  온다」까지만 말한다. 그것을 지금 이 회사·이 조직의 Kit Instance 로 **해석해서
  적어 둔다** — 매 요청 해석하면 앱이 보는 원천이 조용히 바뀐다.

★★★ ③ **해석이 애매하면 만들지 않는다.** 후보가 0개면 「그 데이터를 줄 원천이 이
  조직에 없다」이고, 2개 이상이면 어느 쪽인지 우리가 정할 일이 아니다.
  ⚠️ 「첫 번째를 고른다」는 임의이고 조용하다 — 고른 쪽이 틀리면 남의 숫자를 보여 준다.

★★★ ④ **못 박은 값은 매 요청 대조된다.** 여기서 적은 `kit_instance_id` 가 나중에
  범위 밖이 되면 Dispatch 가 막는다(`api/routes/app_data_runtime.py::_dispatch`).
  못 박기와 대조는 **둘 다** 있어야 한다 — 못 박기만 하면 낡고, 대조만 하면 흔들린다.
"""
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from core import app_runtime_contract as arc
from core.data_preparation import models as dpm


class MaterializeError(Exception):
    """물질화할 수 없다. **아무것도 만들지 않은 상태**로 던진다."""


class Resolved(NamedTuple):
    """계약 데이터셋 하나가 무엇으로 물질화되는가."""
    name: str
    allowed_actions: List[str]
    data_role: str
    source_intent: str
    enterprise_contract_key: str
    kit_instance_id: str
    schema: Dict[str, Any]


class Result(NamedTuple):
    datasets: List[Dict[str, Any]]
    resolved: List[Resolved]


def _contract_datasets(contract: Any) -> List[Dict[str, Any]]:
    if not isinstance(contract, dict):
        raise MaterializeError("계약이 객체가 아닙니다 — 물질화할 대상이 없습니다.")
    if str(contract.get("status") or "") != arc.STATUS_APPROVED:
        #: ⚠️ 승인 전 계약을 물질화하면 검토를 지나지 않은 권한이 DB 에 들어간다.
        #:   그리고 그 결속은 3단계에서 «정상» 으로 봉인된다.
        raise MaterializeError(
            f"승인된 계약만 물질화합니다(현재 {contract.get('status') or '(없음)'}).")
    rows = contract.get("datasets")
    if not isinstance(rows, list) or not rows:
        raise MaterializeError(
            "계약에 데이터셋이 없습니다 — 표가 없는 계약을 물질화하면 앱은 빈 화면을 "
            "정상으로 그린다.")
    return [r for r in rows if isinstance(r, dict)]


def resolve_kit_instance(store: Any, *, contract_key: str, tenant_id: str,
                         scope_node_id: str, entity_mode: str) -> str:
    """이 조직에서 그 업무 데이터를 **실제로 주는** Kit Instance 하나를 찾는다.

    ★★★ 조건은 셋이다: 같은 범위 · 그 계약키의 결속이 있음 · 그 결속이 `ACTIVE`.
      셋을 다 만족하는 것이 **정확히 하나**여야 한다.

    ⚠️ 0개를 「나중에 생기겠지」로 넘기지 않는다. 넘기면 그 앱은 만들어진 첫날부터
      읽을 수 없고, 사용자는 자기가 무엇을 안 했는지 모른다.
    ⚠️ 2개 이상에서 하나를 고르지 않는다 — 그 선택은 임의이고 **조용하다.**"""
    key = str(contract_key or "").strip()
    if not key:
        raise MaterializeError("업무 데이터 계약키가 비었습니다.")

    try:
        candidates = store.list_instances(tenant_id=tenant_id, entity_mode=entity_mode,
                                          scope_node_ids=[scope_node_id])
    except Exception as e:                       # 저장소 장애
        #: ⚠️ 「후보 0개」로 접지 않는다 — 장애와 부재는 다른 사실이고, 부재로 접으면
        #:   운영자가 저장소를 고치러 가지 않는다.
        raise MaterializeError(f"업무 데이터 저장소를 읽을 수 없습니다: {str(e)[:120]}")

    serving = []
    for inst in candidates:
        iid = str(inst.get("instance_id") or "")
        binding = store.active_binding(iid, key)
        if binding and str(binding.get("state")) == dpm.ACTIVE:
            serving.append(iid)

    if not serving:
        raise MaterializeError(
            f"«{key}» 를 제공하는 활성 원천이 이 조직에 없습니다 — 업무 데이터 키트를 "
            f"적용하고 원천을 활성화한 뒤에 앱을 만들 수 있습니다.")
    if len(serving) > 1:
        raise MaterializeError(
            f"«{key}» 를 제공하는 원천이 {len(serving)}개입니다 — 어느 것을 쓸지 "
            f"사람이 정해야 합니다(임의로 고르면 남의 숫자를 보여 줄 수 있습니다).")
    return serving[0]


def plan(contract: Any, *, store: Any, tenant_id: str, scope_node_id: str,
         entity_mode: str) -> List[Resolved]:
    """무엇을 만들지 **먼저 전부 정한다.** 여기서 던지면 아무것도 만들어지지 않았다.

    ★★★ 계획과 실행을 나눈 이유가 ① 이다 — 중간에 실패해도 부분 물질화가 남지 않는다."""
    out: List[Resolved] = []
    problems: List[str] = []

    for ds in _contract_datasets(contract):
        name = str(ds.get("name") or "").strip()
        intent = str(ds.get("source_intent") or "").strip()
        key = str(ds.get("enterprise_contract_key") or "").strip()
        instance_id = ""

        if not name:
            problems.append("이름 없는 데이터셋이 있습니다.")
            continue
        if intent and not arc.materializable(intent):
            status, why = arc.decide_source_intent(intent)
            problems.append(f"{name}: {arc.STATUS_LABEL.get(status, status)} — {why}")
            continue
        if intent == arc.ENTERPRISE_READ:
            try:
                instance_id = resolve_kit_instance(
                    store, contract_key=key, tenant_id=tenant_id,
                    scope_node_id=scope_node_id, entity_mode=entity_mode)
            except MaterializeError as e:
                problems.append(f"{name}: {e}")
                continue
        elif key:
            #: ⚠️ 우리 DB 에서 오는 데이터에 업무 계약키가 붙어 있으면 둘 중 하나가
            #:   틀린 것이다. 조용히 무시하면 그 키는 «적혀 있으나 아무도 안 보는» 값이
            #:   되고, 다음 사람이 그것을 근거로 읽는다.
            problems.append(
                f"{name}: 출처가 {intent or '(없음)'} 인데 업무 데이터 계약키가 "
                f"«{key}» 로 적혀 있습니다 — 둘 중 하나가 틀렸습니다.")
            continue

        out.append(Resolved(
            name=name,
            allowed_actions=[str(a) for a in (ds.get("allowed_actions") or [])],
            data_role=str(ds.get("data_role") or "").strip(),
            source_intent=intent,
            enterprise_contract_key=key,
            kit_instance_id=instance_id,
            schema={"fields": ds.get("fields") or []}))

    if problems:
        #: ★ 하나로 합쳐 던진다 — 한 건씩 고치게 하면 사용자가 같은 화면을 다섯 번 본다.
        raise MaterializeError(" / ".join(problems))
    return out


def materialize(contract: Any, *, release_id: str, actor_id: str, store: Any,
                app_data: Any, tenant_id: str, scope_node_id: str,
                entity_mode: str) -> Result:
    """승인된 계약을 이 릴리스의 데이터셋으로 만든다.

    ★★★ **전부 아니면 아무것도.** `plan()` 이 먼저 전부 해석하고, 그 뒤에야 쓴다.

    ⚠️ 이미 있는 데이터셋은 **이어받는다**(`adopt_dataset`) — 새로 만들면 현업이 쌓은
      레코드가 승계되지 않는다. 그것이 「앱을 개정하면 데이터가 사라진다」의 원인이다."""
    resolved = plan(contract, store=store, tenant_id=tenant_id,
                    scope_node_id=scope_node_id, entity_mode=entity_mode)

    made: List[Dict[str, Any]] = []
    for r in resolved:
        adopted = app_data.adopt_dataset(
            r.name, release_id, allowed_actions=r.allowed_actions, schema=r.schema,
            contract_revision=int((contract or {}).get("revision") or 1),
            data_role=r.data_role, source_intent=r.source_intent,
            enterprise_contract_key=r.enterprise_contract_key,
            kit_instance_id=r.kit_instance_id)
        if adopted is None:
            adopted = app_data.create_dataset(
                release_id, r.name, r.schema, actor_id=actor_id,
                dataset_key=r.name,
                allowed_actions=r.allowed_actions,
                contract_revision=int((contract or {}).get("revision") or 1),
                data_role=r.data_role, source_intent=r.source_intent,
                enterprise_contract_key=r.enterprise_contract_key,
                kit_instance_id=r.kit_instance_id,
                tenant_id=tenant_id, scope_node_id=scope_node_id)
        made.append(adopted)
    return Result(datasets=made, resolved=resolved)
