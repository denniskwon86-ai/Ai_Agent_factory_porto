"""★★★ [I-4 1단계] **HostContractCompiler** — 초안을 계약으로 바꾸는 결정론적 노드.

## 누가 무엇을 하는가

| 주체 | 하는 일 | 하지 않는 일 |
|---|---|---|
| **LLM**(Tech Lead) | 요구 → `capability_intents`·데이터셋 **초안** | 지원 여부 판정 · 지문 계산 |
| **Compiler**(이 파일) | 결정표로 판정 · 검증·정규화 · 의미 지문 | **없는 요구를 지어내기** |
| **사용자** | 축소 / 대기 / Host 기능 확장 중 **선택** | — |

## ★★★ 이 파일은 던지지 않는다

초안은 LLM 이 만든다. 형태가 조금 어긋났다고 예외를 던지면 **스프린트 루프가 통째로 죽는다**
(2026-07-26 에 `ADR` 검증이 정확히 그렇게 죽였다). 그래서 여기서는 오류를 **모아서 돌려주고**
계약은 `DRAFT` 로 남긴다 — 지문도, 승인도, 물질화도 일어나지 않는다. **fail-closed 다.**

## ⚠️ 조용히 고치지 않는다

초안이 매니페스트에 계약에 없는 권한을 적어 두면 그것을 **지우지 않고 오류로 낸다.**
말없이 지우면 사용자가 요구한 것이 사라지고, 아무도 그 사실을 모른다.

## ⚠️⚠️ 지문이 바뀌면 승인은 초기화된다

이전 승인을 새 지문에 끌어다 쓰면 게이트는 아무것도 지키지 않는다.

LLM 0콜.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core import app_manifest, app_runtime_contract as arc


@dataclass
class CompileResult:
    """컴파일 결과. ★ `ok` 가 아니어도 `contract` 는 돌려준다 — 사용자가 무엇이 빠졌는지
    보려면 부분 결과가 필요하다. 다만 그 계약은 `DRAFT` 이고 지문이 비어 있다."""
    contract: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    #: 사용자 선택이 필요한 항목(축소/대기/Host 기능 확장). 화면이 이것으로 선택지를 만든다.
    pending_decisions: List[Dict[str, Any]] = field(default_factory=list)
    #: 이전 계약과 의미 지문이 달라졌는가. 게이트가 이 값으로 재검토 여부를 정한다.
    fingerprint_changed: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return str(self.contract.get("status", ""))

    @property
    def fingerprint(self) -> str:
        return str(self.contract.get("semantic_fingerprint", ""))


def _intent_id(capability: str, requirement_ref: str) -> str:
    """의도 id 는 **결정론적**이다 — 같은 요구를 다시 컴파일해도 같은 id 다.
    (지문에는 들어가지 않지만, 매번 바뀌면 화면의 선택이 엉뚱한 항목에 붙는다.)"""
    seed = f"{capability}\x1f{requirement_ref}"
    return "intent_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]


def _compile_intents(draft: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """의도를 판정한다. ★ 초안이 적어 온 `status` 는 **쓰지 않는다** — 판정은 결정표가 한다."""
    intents: List[Dict[str, Any]] = []
    errors: List[str] = []
    pending: List[Dict[str, Any]] = []
    seen: set = set()

    for raw in (draft.get("capability_intents") or []):
        if not isinstance(raw, dict):
            errors.append(f"capability_intents 항목이 객체가 아닙니다: {raw!r}")
            continue
        cap = str(raw.get("capability", "")).strip()
        if not cap:
            errors.append("capability 가 비어 있는 의도가 있습니다 — 무엇을 요구하는지 알 수 없습니다.")
            continue
        ref = str(raw.get("requirement_ref", "")).strip()
        status, reason = arc.decide(cap)
        iid = _intent_id(cap, ref)
        if iid in seen:
            continue
        seen.add(iid)

        decision = str(raw.get("user_decision", "")).strip()
        if decision:
            if arc.is_buildable(status):
                # 지원되는 요구에 결정이 붙어 있으면 초안이 상태를 잘못 알고 있었다는 뜻이다.
                #
                # ★★★ [2026-08-26 실측] 그러나 **막지는 않는다.** 여기서 이미 값을 버리므로
                #   (`decision = ""`) 계약에는 아무 영향이 없다 — 권한도, 지문도, 승인도.
                #   그런데 종전에는 이 잉여 칸 하나로 **프로젝트 전체가 CONTRACT_BLOCKED** 였다.
                #   실측: Tech Lead 가 `app_data.query`(CONDITIONAL)에 `WAIT` 을 붙였고
                #   7개 태스크짜리 프로젝트가 그 자리에서 멈췄다. 통제가 지키는 것이 없는데
                #   완주만 막는다 — 그런 거절은 통제가 아니라 마찰이다.
                # ⚠️ 조용히 넘기지도 않는다. 초안이 상태를 잘못 안 것은 **사실**이므로
                #   말하고 지운다. 다음 초안이 같은 실수를 반복하면 로그에 남는다.
                # ⚠️ 정본 검증기(`arc.validate` 규칙)는 **그대로 둔다.** 어떤 경로로든 이 값이
                #   계약까지 실려 가면 거기서 막힌다 — 층마다 가정이 달라야 층이다.
                print(f"ℹ️ [ContractCompiler] {cap}: 상태가 {status} 인데 "
                      f"user_decision {decision!r} 이 붙어 있습니다 — 고를 것이 없는 "
                      f"자리이므로 **버리고 계속합니다.**")
                decision = ""
            elif decision not in arc.allowed_decisions(status):
                # ★★★ 금지 항목의 `REQUEST_HOST_FEATURE` 가 여기서 막힌다.
                errors.append(
                    f"{cap}: {arc.STATUS_LABEL.get(status, status)} 에는 {decision} 를 "
                    f"고를 수 없습니다(가능: {list(arc.allowed_decisions(status))}).")
                decision = ""

        intents.append({
            "intent_id": iid,
            "requirement_ref": ref,
            "capability": cap,
            "status": status,
            "reason": reason,
            "user_decision": decision,
        })
        if not arc.is_buildable(status) and not decision:
            pending.append({
                "intent_id": iid, "requirement_ref": ref, "capability": cap,
                "status": status, "status_label": arc.STATUS_LABEL.get(status, status),
                "reason": reason, "choices": list(arc.allowed_decisions(status)),
            })
    return intents, errors, pending


def _compile_datasets(draft: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """데이터셋을 정규화한다. ⚠️ **없는 값을 채우지 않는다** — 특히 `classification` 은
    비어 있으면 오류다. 등급을 지어내면 없느니만 못하다(그 값으로 공유 판단을 하게 된다)."""
    out: List[Dict[str, Any]] = []
    errors: List[str] = []
    for raw in (draft.get("datasets") or []):
        if not isinstance(raw, dict):
            errors.append(f"datasets 항목이 객체가 아닙니다: {raw!r}")
            continue
        name = str(raw.get("name", "")).strip()
        ds: Dict[str, Any] = {
            "name": name,
            "label": str(raw.get("label", "")).strip() or name,
            "purpose": str(raw.get("purpose", "")).strip(),
            # 순서를 고정한다 — 같은 집합이 다른 순서로 오면 지문이 흔들린다.
            "allowed_actions": [a for a in arc.ACTIONS
                                if a in {str(x) for x in (raw.get("allowed_actions") or [])}],
            "fields": [],
        }
        #: [BDR-1] 출처·역할·중복입력은 **정규화만** 한다 — 없으면 지어내지 않는다.
        #: ⚠️⚠️ 빠졌을 때 `AFS_NATIVE` 를 채워 넣으면 그 순간 「기존 시스템에 있는 값을
        #:   화면에서 또 받는」 앱이 된다. 빠진 것은 빠진 채로 스키마가 거부한다.
        for k in ("data_role", "source_intent", "duplicate_entry_policy",
                  "ontology_entity_type", "knowledge_eligibility",
                  "enterprise_contract_key", "required_freshness"):
            v = str(raw.get(k, "")).strip()
            if v:
                ds[k] = v

        #: ★★★ 출처 결정표(§6.3). **지금 물질화되는 것은 `AFS_NATIVE` 뿐이다.**
        intent = str(ds.get("source_intent", ""))
        if intent and not arc.materializable(intent):
            status, why = arc.decide_source_intent(intent)
            errors.append(
                f"{name or '?'}: {arc.STATUS_LABEL.get(status, status)} — {why}")
        #: ★★★ [Wave F-0] **이중 입력 게이트를 여기서 실제로 돌린다.**
        #:
        #: ⚠️⚠️ 그전까지 이 게이트는 컴파일 경로에서 **한 번도 실행되지 않았다.**
        #:   `ENTERPRISE_READ` 가 「아직 물질화 불가」로 먼저 막혔고, 그 안내문에 마침
        #:   「입력 화면」이라는 말이 들어 있어서 시험이 통과했다 — 게이트가 아니라
        #:   **문구가 통과시키고 있었다.** 출처를 열자 그 우연한 방벽이 사라졌다.
        #: ★ `role_source_errors` 하나만 부른다 — 규칙을 여기에 다시 적으면 두 판정이
        #:   갈라지고, 갈린 사이에 만들어진 결속이 3단계에서 정상으로 봉인된다.
        role = str(ds.get("data_role", ""))
        if intent and role:
            errors.extend(f"{name or '?'}: {e}"
                          for e in arc.role_source_errors(role, intent,
                                                          ds["allowed_actions"]))

        #: ★★★ [Wave F-0] 사내 원천이라고 말했으면 **어느 표인지도 말해야 한다.**
        #: ⚠️ 이 검사가 없으면 계약은 조용히 통과하고, 그 데이터셋은 **런타임에서
        #:   영원히 「읽을 수 없음」** 이 된다. 만들 때 아무 말이 없다가 쓸 때 실패하면
        #:   사용자는 자기 파일을 의심한다 — 실패는 만드는 자리로 옮긴다.
        if intent == arc.ENTERPRISE_READ and not str(ds.get("enterprise_contract_key", "")):
            errors.append(
                f"{name or '?'}: 출처가 {arc.ENTERPRISE_READ} 인데 어느 업무 데이터에서 "
                f"오는지(`enterprise_contract_key`)가 없습니다 — 원천을 특정하지 않으면 "
                f"이 데이터는 만들어져도 읽히지 않습니다.")
        unknown = [a for a in {str(x) for x in (raw.get("allowed_actions") or [])}
                   if a not in arc.ACTIONS]
        if unknown:
            errors.append(f"{name or '?'}: 알 수 없는 행동 {sorted(unknown)} — "
                          f"가능한 것은 {list(arc.ACTIONS)} 입니다.")
        for f in (raw.get("fields") or []):
            if not isinstance(f, dict):
                errors.append(f"{name or '?'}: fields 항목이 객체가 아닙니다: {f!r}")
                continue
            fd: Dict[str, Any] = {
                "name": str(f.get("name", "")).strip(),
                "type": str(f.get("type", "")).strip(),
                "required": bool(f.get("required", False)),
                "classification": str(f.get("classification", "")).strip(),
            }
            for k in ("label", "business_term_id", "semantic_role", "unit", "master_reference"):
                v = str(f.get(k, "")).strip()
                if v:
                    fd[k] = v
            ds["fields"].append(fd)
        out.append(ds)
    return out, errors


def _derive_manifest(datasets: List[Dict[str, Any]],
                     app_class: str) -> Tuple[Dict[str, Any], List[str]]:
    """계약에서 매니페스트를 만든다 — 계약이 정본이고 매니페스트는 그 투영이다.

    ⚠️ `app_manifest.build()` 는 던진다. 여기서 새어 나가면 이 파일의 「던지지 않는다」가
      거짓이 되므로 오류로 바꿔 담는다."""
    caps = [{"resource": ds["name"], "actions": list(ds.get("allowed_actions") or [])}
            for ds in datasets if ds.get("name")]
    try:
        return app_manifest.build(capabilities=caps, app_class=app_class), []
    except app_manifest.ManifestError as e:
        return app_manifest.minimal(), [f"manifest 를 만들 수 없습니다: {e}"]


def _unsupported(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """결정이 끝난 미지원 요구만 계약에 싣는다.

    ⚠️ 결정이 없는 것을 실으면 「사용자가 대기를 선택했다」와 「아직 아무도 안 봤다」가
      같은 모양이 된다. 그 둘은 다르다 — 결정 전에는 계약이 성립하지 않는다."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for i in intents:
        if arc.is_buildable(i["status"]) or not i["user_decision"]:
            continue
        key = (i["requirement_ref"], i["status"], i["user_decision"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"requirement_ref": i["requirement_ref"], "status": i["status"],
                    "reason": i["reason"], "user_decision": i["user_decision"]})
    return out


def compile_contract(draft: Any, *, project_id: str, task_id: str = "",
                     previous: Optional[Dict[str, Any]] = None) -> CompileResult:
    """초안 → 계약. **결정론적이고, 던지지 않는다.**

    같은 입력에 같은 출력을 준다(id·지문·순서 모두 내용에서 유도한다).
    오류가 하나라도 있으면 `status="DRAFT"` 이고 지문은 비어 있다 — 그 계약으로는
    승인도 물질화도 일어나지 않는다."""
    d = draft if isinstance(draft, dict) else {}
    errors: List[str] = []
    if not isinstance(draft, dict):
        errors.append("초안이 객체가 아닙니다.")

    intents, ierr, pending = _compile_intents(d)
    datasets, derr = _compile_datasets(d)
    errors.extend(ierr)
    errors.extend(derr)

    app_class = str(d.get("app_class", "")).strip()
    if app_class not in app_manifest.APP_CLASSES:
        errors.append(f"app_class 가 {list(app_manifest.APP_CLASSES)} 중 하나여야 합니다"
                      f"(현재 {app_class or '(없음)'}) — 분류 없이는 권한 판단을 할 수 없습니다.")

    derived, merr = _derive_manifest(
        datasets, app_class if app_class in app_manifest.APP_CLASSES else "")
    errors.extend(merr)
    given = d.get("manifest")
    if isinstance(given, dict) and given:
        # ⚠️ 초안이 준 매니페스트를 말없이 갈아 끼우지 않는다 — 어긋나면 그것을 보고한다.
        extra = sorted(set(given.get("capabilities") or []) - set(derived["capabilities"]))
        if extra:
            errors.append(f"manifest 에 계약 밖 권한이 있습니다: {extra} — "
                          f"계약을 고치거나 그 권한을 빼야 합니다.")
    manifest = derived

    if pending:
        errors.append(
            "사용자 결정이 필요한 요구가 "
            + ", ".join(f"{p['capability']}({p['status_label']})" for p in pending)
            + " 있습니다.")

    contract: Dict[str, Any] = {
        "schema_version": arc.SCHEMA_VERSION,
        "contract_id": arc.contract_id_for(project_id, task_id),
        "revision": 1,
        "project_id": str(project_id or ""),
        "task_id": str(task_id or ""),
        "runtime_contract_version": arc.RUNTIME_CONTRACT_VERSION,
        "status": "DRAFT",
        "app_class": app_class,
        "capability_intents": intents,
        "manifest": manifest,
        "datasets": datasets,
        "unsupported_requirements": _unsupported(intents),
        "semantic_fingerprint": "",
        "approval": {"status": "PENDING"},
    }

    prev_fp = str((previous or {}).get("semantic_fingerprint", ""))
    prev_rev = int((previous or {}).get("revision", 0) or 0)

    if errors:
        # DRAFT 로 남긴다. 지문 없음 = 승인할 대상 없음.
        return CompileResult(contract=contract, errors=errors, pending_decisions=pending,
                             fingerprint_changed=bool(prev_fp))

    fp = arc.semantic_fingerprint(contract)
    contract["semantic_fingerprint"] = fp
    contract["status"] = "COMPILED"
    changed = bool(previous) and fp != prev_fp
    contract["revision"] = (prev_rev + 1) if changed else max(prev_rev, 1)

    # ★★★ 지문이 같을 때만 이전 승인을 잇는다. 다르면 PENDING 으로 돌아간다.
    if previous and not changed:
        prev_ap = (previous or {}).get("approval")
        if isinstance(prev_ap, dict) and prev_ap.get("status") == "APPROVED":
            contract["approval"] = dict(prev_ap)
            contract["status"] = "APPROVED"

    # 마지막으로 자기 자신을 정본 검증기에 통과시킨다 — 컴파일러의 실수를 컴파일러가
    # 봐주지 않게 한다.
    late = arc.validate(contract)
    if late:
        contract["status"] = "DRAFT"
        contract["semantic_fingerprint"] = ""
        return CompileResult(contract=contract, errors=late, pending_decisions=pending,
                             fingerprint_changed=changed)

    return CompileResult(contract=contract, errors=[], pending_decisions=[],
                         fingerprint_changed=changed)
