"""★★★ [M0-5] 경로 계산 **관문별 준비도** — 「왜 시연이 안 도는가」에 한 곳에서 답한다.

## 왜 필요했는가

계산이 막히면 실행기는 `BLOCKED` 와 사유를 준다. 그런데 그 사유는 **계산을 시도한
뒤**에야 나오고, 시도하려면 먼저 인스턴스·경로·질문이 있어야 한다. 운영자가 시연 전에
「지금 무엇이 빠졌나」를 물을 곳이 없었다.

## ⚠️⚠️ 이 파일의 규칙 — 셋을 갈라 놓는다

| 상태 | 뜻 | 화면이 해야 할 일 |
|---|---|---|
| `READY` | 됐다 | 다음 관문 |
| `NOT_YET` | **아직 안 했다** — 사람이 할 일이 남았다 | 그 일을 안내한다 |
| `FAILED` | **확인하지 못했다** — 저장소·원장 장애 | 재시도·담당자 호출 |

⚠️⚠️ `FAILED` 를 `NOT_YET` 으로 접지 않는다. 접으면 원장이 죽은 동안 화면이 「승인이
  없습니다」를 띄우고, 운영자는 승인을 다시 요청한다 — 몇 번을 해도 같다. 이 저장소는
  같은 유형을 승인 판정기·소유권 결속·인증판 판독에서 이미 세 번 고쳤다.

⚠️ **없는 것을 0으로 적지 않는다.** 「인증판 0건」과 「인증판을 세지 못했다」는 다른 답이다.

LLM 호출: 0건.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core import calc_capability as cc
from core import calc_dataset_loader as loader
from core import path_calculation as pc

READY = "READY"
NOT_YET = "NOT_YET"
FAILED = "FAILED"

#: 관문 순서 — 앞이 안 되면 뒤는 **판정하지 않는다**(「모른다」와 「안 됐다」는 다르다).
GATES = ("kit", "instance", "snapshots", "baseline", "capabilities")


def _gate(name: str, state: str, *, summary: str, action: str = "",
          detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"gate": name, "state": state, "summary": summary,
            "next_action": action, "detail": dict(detail or {})}


def _skipped(name: str, because: str) -> Dict[str, Any]:
    """앞 관문이 안 서서 **판정하지 않은** 관문.

    ⚠️ 이것을 `NOT_YET` 으로 적지 않는다. 「아직 안 했다」는 사실 주장이고, 여기서는
      확인조차 하지 않았다 — 확인하지 않은 것을 결론으로 적으면 화면이 없는 일을
      시킨다(앞 관문을 먼저 풀면 이 관문은 이미 서 있을 수도 있다)."""
    return {"gate": name, "state": "UNKNOWN", "summary": f"앞 관문이 서지 않아 확인하지 않았습니다({because}).",
            "next_action": "", "detail": {}}


def evaluate(store: Any, *, instance: Optional[Dict[str, Any]],
             kit_id: str, kit_version: str) -> Dict[str, Any]:
    """관문별 준비도. `instance` 는 **호출부가 가시성 판정을 마친 행**이어야 한다.

    ⚠️ 여기서 권한을 판정하지 않는다 — 판정을 두 벌로 만들면 한쪽만 고쳐진다.
      못 보는 인스턴스는 호출부가 404 로 답하고 여기까지 오지 않는다."""
    gates: List[Dict[str, Any]] = []

    # ── ① 키트 등록 ───────────────────────────────────────────────────
    from core.data_preparation import kit_registry

    try:
        kit = kit_registry.resolve(store, kit_id, kit_version)
    except Exception as exc:  # noqa: BLE001 — 판독 실패는 «없음» 이 아니다
        gates.append(_gate("kit", FAILED,
                           summary=f"등록부를 읽지 못했습니다: {exc}",
                           action="저장소 상태를 확인한 뒤 다시 시도하십시오."))
        return _wrap(gates)
    if not kit:
        gates.append(_gate("kit", NOT_YET,
                           summary=f"정본 키트가 등록되지 않았습니다({kit_id}@{kit_version}).",
                           action="키트 프로파일을 등록하십시오."))
        return _wrap(gates + [_skipped(g, "키트 미등록") for g in GATES[1:]])
    gates.append(_gate("kit", READY, summary=f"{kit_id}@{kit_version} 등록됨",
                       detail={"kit_fingerprint": str(kit.get("kit_fingerprint", ""))}))

    # ── ② 인스턴스 ────────────────────────────────────────────────────
    if not instance:
        gates.append(_gate("instance", NOT_YET,
                           summary="이 키트의 인스턴스가 없습니다.",
                           action="키트 인스턴스를 만드십시오."))
        return _wrap(gates + [_skipped(g, "인스턴스 없음") for g in GATES[2:]])
    ctx = {"instance_id": str(instance["instance_id"]),
           "tenant_id": str(instance["tenant_id"]),
           "entity_mode": str(instance["entity_mode"]),
           "scope_node_id": str(instance["scope_node_id"])}
    gates.append(_gate("instance", READY, summary="인스턴스 있음", detail=dict(ctx)))

    # ── ③ 인증판 ──────────────────────────────────────────────────────
    try:
        seals = loader.active_seals(store, instance_id=ctx["instance_id"],
                                    contract_keys=pc.REQUIRED_DATASETS)
    except Exception as exc:  # noqa: BLE001
        gates.append(_gate("snapshots", FAILED,
                           summary=f"인증판을 세지 못했습니다: {exc}",
                           action="저장소 상태를 확인한 뒤 다시 시도하십시오."))
        return _wrap(gates + [_skipped(g, "인증판 판독 실패") for g in GATES[3:]])
    missing = sorted(set(pc.REQUIRED_DATASETS) - set(seals))
    if missing:
        gates.append(_gate("snapshots", NOT_YET,
                           summary=f"인증판이 없는 계약키 {len(missing)}건",
                           action="해당 자료를 올리고 인증하십시오.",
                           detail={"missing_contract_keys": missing,
                                   "certified": sorted(seals)}))
    else:
        gates.append(_gate("snapshots", READY,
                           summary=f"필수 {len(pc.REQUIRED_DATASETS)}종 모두 인증됨",
                           detail={"used_snapshots": dict(seals)}))

    # ── ④ 계산 기준선 봉인 ────────────────────────────────────────────
    from core import calc_baseline as cb

    try:
        base = cb.active(store, instance_id=ctx["instance_id"], tenant_id=ctx["tenant_id"],
                         entity_mode=ctx["entity_mode"], scope_node_id=ctx["scope_node_id"])
    except Exception as exc:  # noqa: BLE001
        gates.append(_gate("baseline", FAILED,
                           summary=f"기준선 봉인을 확인하지 못했습니다: {exc}",
                           action="원장·저장소 상태를 확인한 뒤 다시 시도하십시오."))
        return _wrap(gates + [_skipped("capabilities", "기준선 확인 실패")])
    if not base:
        #: ⚠️ 빈 기준선으로 계산하면 모든 판매행이 `missing_baseline` 이 되고, 그것이
        #:   화면에서 「영향 없음」으로 읽힌다. 그래서 없는 것은 «준비 안 됨» 이다.
        gates.append(_gate("baseline", NOT_YET,
                           summary="봉인된 계산 기준선이 없습니다.",
                           action="배분·인식 규칙·기준 인식일을 봉인하십시오."))
    else:
        gates.append(_gate("baseline", READY, summary="기준선 봉인됨",
                           detail={"build_id": str(base.get("build_id", "")),
                                   "fingerprint": str(base.get("fingerprint", ""))}))

    # ── ⑤ 계산 능력 실행 승인 ─────────────────────────────────────────
    #: ★★★ 등록부의 `state` 만 읽지 않는다 — 그것은 「그때 그랬다」이고, **철회는 등록부를
    #:   고치지 않는다.** `assert_executable` 에 실제 원장 검증기를 태운다.
    from core import path_calculation_service as svc

    try:
        verifier = svc.context_verifier(
            store, instance_id=ctx["instance_id"], tenant_id=ctx["tenant_id"],
            entity_mode=ctx["entity_mode"], scope_node_id=ctx["scope_node_id"])
        resolver = svc.context_resolver(
            store, instance_id=ctx["instance_id"], tenant_id=ctx["tenant_id"],
            entity_mode=ctx["entity_mode"], scope_node_id=ctx["scope_node_id"])
    except Exception as exc:  # noqa: BLE001 — 결속을 만들지 못했다
        gates.append(_gate("capabilities", FAILED,
                           summary=f"실행 승인 조건을 산출하지 못했습니다: {exc}",
                           action="저장소·구현 파일 상태를 확인한 뒤 다시 시도하십시오."))
        return _wrap(gates)
    pending: List[str] = []
    broken: List[Dict[str, str]] = []
    unreadable = ""
    for ref in pc.SEGMENTS:
        try:
            cap = resolver(ref)
            cc.assert_executable(ref, verifier, capability=cap)
        except cc.CapabilityError as exc:
            state = ""
            try:
                state = str(resolver(ref).state)
            except Exception:  # noqa: BLE001
                pass
            broken.append({"ref": ref, "state": state, "reason": str(exc)})
            pending.append(ref)
        except Exception as exc:  # noqa: BLE001 — 원장 장애
            #: ⚠️ 여기 오는 것은 판독 실패다. 「승인 없음」과 섞지 않는다.
            unreadable = str(exc)
            break
    if unreadable:
        gates.append(_gate("capabilities", FAILED,
                           summary=f"실행 승인을 확인하지 못했습니다: {unreadable}",
                           action="원장 상태를 확인한 뒤 다시 시도하십시오."))
    elif pending:
        gates.append(_gate("capabilities", NOT_YET,
                           summary=f"실행 승인이 없는 계산 {len(pending)}건",
                           action="계산 능력 실행을 승인하십시오(사람의 결정 + 원장 사건).",
                           detail={"pending": broken}))
    else:
        gates.append(_gate("capabilities", READY,
                           summary=f"계산 {len(pc.SEGMENTS)}종 실행 승인됨"))

    return _wrap(gates)


def _wrap(gates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """관문 목록 → 전체 판정.

    ⚠️ **하나라도 `FAILED` 면 전체가 `FAILED` 다.** 「나머지는 됐으니 부분 가능」으로
      적으면 장애가 진행 상황처럼 보인다."""
    states = [g["state"] for g in gates]
    if FAILED in states:
        status = FAILED
    elif "UNKNOWN" in states or NOT_YET in states:
        status = NOT_YET
    else:
        status = READY
    return {
        "status": status,
        "gates": gates,
        #: ★ **다음에 할 일 하나**를 뽑아 준다 — 목록만 주면 어디부터인지 모른다.
        "next_action": next((g["next_action"] for g in gates
                             if g["state"] in (NOT_YET, FAILED) and g["next_action"]), ""),
        #: ⚠️ 「몇 개 남았나」를 세되, **확인하지 않은 관문은 남은 수에 넣지 않는다** —
        #:   그 수는 사실이 아니다.
        "counts": {"ready": states.count(READY), "not_yet": states.count(NOT_YET),
                   "failed": states.count(FAILED), "unknown": states.count("UNKNOWN")},
    }
