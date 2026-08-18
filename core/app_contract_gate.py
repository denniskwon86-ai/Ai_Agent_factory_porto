"""★★★ [I-4 3단계] **증명 발급 전 일치 게이트 + 두 지문.**

## 왜 «봉인» 만으로는 부족한가

지문을 증명에 봉인하면 **발급 뒤의 변경**은 잡는다. 그러나 **처음부터 계약과 DB 결속이
다른 상태**에는 아무 말도 하지 않는다 — 그 상태에서 발급된 증명은 «어긋난 상태» 를 정상으로
못박고, 이후 모든 대조가 그 어긋남을 기준으로 삼는다.

    봉인은 「그때와 같은가」에 답할 뿐 **「그때가 옳았는가」에는 답하지 않는다.**

그래서 발급 **전에** 승인된 계약과 실제 물질화를 **데이터셋별로** 대조한다.

## 대조하는 것

    데이터셋 수 · runtime_name / dataset_key · 스키마 지문
    · allowed_actions · data_role / source_intent · contract_bound=1

## 발급하지 않는 경우

· 계약 데이터셋이 물질화되지 않음        · 계약에 없는 결속이 추가됨
· 역할·출처·행동·스키마가 다름           · 계약이 승인되지 않음
· 계약이나 물질화 상태를 판독할 수 없음

★ **데이터셋 0개 앱은 정상이다** — 「계약 0개 + 결속 0개」이면 통과한다. 0을 오류로 만들면
  화면만 있는 앱을 만들 수 없다.

## 두 지문은 **다른 사실**이다

| 지문 | 무엇의 사실 |
|---|---|
| `contract_fingerprint` | 승인된 **계약 원문** |
| `materialization_fingerprint` | 실제 **DB 결속 상태** |

⚠️ 원문만 봉인하면 「계약서는 승인됐지만 결속이 다른 상태」를 잡을 수 없고, 물질화만
봉인하면 「같은 결속인데 계약이 개정된 상태」를 놓친다.

LLM 0콜.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core import app_runtime_contract as arc
from core.app_data import app_data_service

#: ★★★ 계약이 **없는** 릴리스의 지문. 빈 문자열이 아니라 **표식**이다.
#:
#: ⚠️⚠️ 빈 값으로 두면 판정이 「양쪽 다 비었으니 같다」로 통과한다. 그러면 계약이 **나중에
#:   생겨도** 이미 도는 앱은 그대로 살아 있고, 승인 없는 상태로 계속 데이터를 만진다.
#:   표식을 쓰면 계약이 생기는 순간 지문이 달라지고 그 프레임은 폐기된다.
NO_CONTRACT = "no-contract"

#: 판독 실패의 표식. ⚠️ 이것이 봉인되는 일은 없다 — 판독 실패면 발급 자체가 막힌다.
UNREADABLE = "unreadable"


@dataclass
class GateVerdict:
    """발급해도 되는가. **막는 이유를 사람이 읽을 문장으로** 함께 준다."""
    ok: bool
    reasons: List[str] = field(default_factory=list)
    contract_fingerprint: str = ""
    materialization_fingerprint: str = ""
    #: 계약이 아예 없는 릴리스(레거시)인가 — 「없다」와 「어긋난다」는 다른 사실이다.
    legacy: bool = False


def release_contract(release: Any) -> Optional[Dict[str, Any]]:
    """릴리스에 봉인된 계약 스냅샷. 없으면 `None`.

    ★ 정본은 workspace 파일이지만 **그 릴리스가 실제로 쓴 판**은 `release.json` 에 있다
      (설계 §4 — 릴리스 봉인). 발급 판정은 「지금 도는 이 릴리스」를 봐야 하므로 이쪽이다."""
    if not isinstance(release, dict):
        return None
    c = release.get("runtime_contract")
    return c if isinstance(c, dict) and c else None


#: 승인이 아직/더 이상 없는 계약의 표식.
#:
#: ⚠️⚠️ **승인 상태는 의미 지문에 들어가지 않는다**(문구·승인자가 바뀌었다고 재승인을
#:   요구하면 게이트가 습관이 된다). 그래서 승인이 **취소돼도 지문은 그대로**이고,
#:   이미 도는 앱은 아무 일 없이 계속 데이터를 만진다 — 승인이 사라졌는데도.
#:   그 구멍을 여기서 닫는다: 승인되지 않은 계약은 **다른 값**을 낸다.
UNAPPROVED = "unapproved"


def contract_fingerprint(release: Any) -> str:
    """계약 원문 지문. 계약이 없으면 표식, 승인이 없으면 미승인 표식, 못 읽으면 실패 표식.

    ★ 세 표식은 서로 다른 사실이다 — 「계약이 없다」·「승인되지 않았다」·「읽을 수 없다」."""
    c = release_contract(release)
    if c is None:
        return NO_CONTRACT
    try:
        if str((c.get("approval") or {}).get("status", "")) != "APPROVED":
            return UNAPPROVED
        return arc.semantic_fingerprint(c)
    except Exception:                                  # pragma: no cover - 방어
        return UNREADABLE


def _contract_datasets(contract: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for ds in (contract.get("datasets") or []):
        if isinstance(ds, dict) and str(ds.get("name", "")):
            out[str(ds["name"])] = ds
    return out


def _materialized(release_id: str) -> Dict[str, Dict[str, Any]]:
    """이 릴리스의 **계약 결속**들을 런타임 이름으로 모은다(레거시 결속은 따로 센다)."""
    rows = app_data_service._store.query(
        "SELECT b.runtime_name AS name, b.allowed_actions AS actions, b.contract_bound AS bound, "
        "       b.data_role AS data_role, b.source_intent AS source_intent, "
        "       d.dataset_key AS dataset_key, COALESCE(v.schema_fingerprint,'') AS schema_fp "
        "  FROM app_release_dataset_bindings b "
        "  JOIN app_datasets d ON d.dataset_id = b.dataset_id "
        "  LEFT JOIN app_dataset_versions v ON v.version_id = b.version_id "
        " WHERE b.release_id=?", ((release_id or "").strip(),))
    return {str(r["name"]): dict(r) for r in rows}


def _compare(contract: Dict[str, Any], bound: Dict[str, Dict[str, Any]]) -> List[str]:
    """★★★ **데이터셋별 대조.** 한 축이라도 다르면 이유를 남긴다."""
    want = _contract_datasets(contract)
    reasons: List[str] = []

    missing = sorted(set(want) - set(bound))
    if missing:
        reasons.append(f"계약에 있는 데이터셋이 물질화되지 않았습니다: {missing}")
    extra = sorted(n for n in set(bound) - set(want) if int(bound[n].get("bound") or 0))
    if extra:
        #: ⚠️ 계약에 없는 결속은 «승인되지 않은 권한» 이다 — 관리 경로가 몰래 더한 것이다.
        reasons.append(f"계약에 없는 결속이 있습니다: {extra}")
    stray_legacy = sorted(n for n in set(bound) - set(want) if not int(bound[n].get("bound") or 0))
    if stray_legacy:
        #: ⚠️⚠️ 계약이 있는 릴리스에 **레거시 결속**이 섞여 있다. 그 데이터셋은 2차 판정이
        #:   없으므로(레거시 = 계약이 말한 적 없음) 앱이 **아무 제한 없이** 만진다.
        #:   「계약 밖」과 다른 사유로 말한다 — 고칠 방법이 다르다(계약에 넣거나 폐지한다).
        reasons.append(f"계약이 있는 릴리스에 계약 이전 결속이 남아 있습니다: {stray_legacy} — "
                       f"그 데이터셋에는 계약 판정이 걸리지 않습니다.")

    for name in sorted(set(want) & set(bound)):
        w, g = want[name], bound[name]
        if not int(g.get("bound") or 0):
            reasons.append(f"{name}: 계약 결속이 아닙니다(contract_bound=0) — "
                           f"계약이 정한 데이터셋인데 레거시로 물질화돼 있습니다.")
        want_actions = ",".join(a for a in arc.ACTIONS
                                if a in {str(x) for x in (w.get("allowed_actions") or [])})
        if str(g.get("actions") or "") != want_actions:
            reasons.append(f"{name}: 허용 행동이 다릅니다"
                           f"(계약 {want_actions or '(없음)'} · 결속 {g.get('actions') or '(없음)'})")
        for key, label in (("data_role", "역할"), ("source_intent", "출처")):
            if str(g.get(key) or "") != str(w.get(key, "") or ""):
                reasons.append(f"{name}: {label}이 다릅니다"
                               f"(계약 {w.get(key) or '(없음)'} · 결속 {g.get(key) or '(없음)'})")
        want_key = str(w.get("dataset_key", "") or name)
        if str(g.get("dataset_key") or "") != want_key:
            reasons.append(f"{name}: 안정 키가 다릅니다"
                           f"(계약 {want_key} · 결속 {g.get('dataset_key') or '(없음)'})")
        want_fp = _schema_fp(w)
        if want_fp and str(g.get("schema_fp") or "") != want_fp:
            reasons.append(f"{name}: 스키마 판이 다릅니다 — 계약이 승인한 판과 저장된 판이 "
                           f"같지 않습니다.")
    return reasons


def _schema_fp(dataset: Dict[str, Any]) -> str:
    """계약이 선언한 필드로부터 판 지문을 계산한다(물질화가 저장한 값과 같은 규칙)."""
    from core.app_data import schema_fingerprint
    fields = []
    for f in (dataset.get("fields") or []):
        if isinstance(f, dict) and f.get("name"):
            fields.append({"name": str(f["name"]), "type": str(f.get("type", "string")),
                           "required": bool(f.get("required", False)),
                           "label": str(f.get("label", "") or f["name"])})
    if not fields:
        return ""
    try:
        return schema_fingerprint({"fields": fields})
    except Exception:                                  # pragma: no cover - 방어
        return ""


def release_contract_profile(release: Any) -> str:
    """[I-4 4c-7] 이 릴리스가 **계약 절차를 켠 프로젝트**에서 나왔는가.

    ⚠️ 판독 실패·미지정은 `""` 다 — 여기서 켜면 계약 이전에 만든 모든 릴리스가
      즉시 막힌다. 소급하지 않는 경계는 `runtime_contract_profile` 하나뿐이고,
      그 값을 릴리스가 **자기 안에 들고 있어야** 나중에 프로젝트 메타가 바뀌어도
      「이 판이 어떤 규칙으로 만들어졌는가」가 흔들리지 않는다."""
    from core.wbs_artifact_kind import PROFILE_V1, profile_enforces_contract

    if not isinstance(release, dict):
        return ""
    raw = release.get("runtime_contract_profile", "")
    return PROFILE_V1 if profile_enforces_contract(raw) else ""


def is_executable_app_in_app(release: Any) -> bool:
    """이 릴리스가 **사용자가 실행하는 App-in-App** 인가.

    ★★★ [설계 §15 · 4c-7] `artifact_kind` 는 기획이 **선언**한 값이라, 유효하지만
      틀릴 수 있다 — LLM 이 실행 앱을 `REPORT` 로 분류하면 그 태스크는 계약 대상에서
      빠지고, 만들어진 앱은 계약 없이 데이터를 만진다. 분류를 믿지 않고 **결과물**을
      본다.

    ⚠️ 판독할 수 없으면 **실행 가능한 것으로 본다.** 「모르면 면제」는 곧 우회로이고,
      여기서 잘못 면제하면 승인 없는 앱이 열린다."""
    if not isinstance(release, dict):
        return True
    #: 명시적 예외 모드(설계 §4) — 사람이 「이것은 Host 런타임을 쓰지 않는다」고 적은 판.
    if release.get("requires_host_runtime") is False:
        return False
    kind = str(release.get("artifact_kind", "") or "").strip().upper()
    if kind in ("REPORT", "DOCUMENT", "LIBRARY"):
        #: ⚠️ 선언만으로 면제하지 않는다. 실행 산출물의 흔적이 있으면 **선언이 틀린 것**이다.
        snap = release.get("manifest") or {}
        man = snap.get("manifest") if isinstance(snap, dict) else None
        if (man or {}).get("capabilities"):
            return True
        if str(release.get("view_type", "") or "").strip():
            return True
        return False
    return True


def evaluate(release: Any, release_id: str) -> GateVerdict:
    """★★★ **발급해도 되는가.** 던지지 않는다 — 호출부가 HTTP 로 바꾼다."""
    rid = (release_id or "").strip()
    contract = release_contract(release)

    try:
        bound = _materialized(rid)
    except Exception as e:
        #: ⚠️ 물질화를 못 읽으면 **발급하지 않는다.** 「모르니까 통과」가 곧 승인 없는 권한이다.
        return GateVerdict(ok=False, reasons=[f"물질화 상태를 읽을 수 없습니다: {str(e)[:80]}"])

    try:
        mat_fp = app_data_service.materialization_fingerprint(rid)
    except Exception as e:
        return GateVerdict(ok=False, reasons=[f"물질화 지문을 만들 수 없습니다: {str(e)[:80]}"])

    if contract is None:
        #: 계약이 **없는** 릴리스. 계약 결속도 없어야 한다 —
        #: ⚠️⚠️ 결속만 있고 계약이 없다면 **물질화가 승인보다 앞선** 상태이고, 그것은
        #:   「아무도 승인하지 않은 권한이 열려 있다」는 뜻이다.
        rogue = sorted(n for n, g in bound.items() if int(g.get("bound") or 0))
        if rogue:
            return GateVerdict(
                ok=False, materialization_fingerprint=mat_fp,
                reasons=[f"승인된 계약이 없는데 계약 결속이 있습니다: {rogue} — "
                         f"아무도 승인하지 않은 권한이 열려 있습니다."])
        #: ★★★ [4c-7] **실행 가능한 앱은 레거시 면제를 받을 수 없다.**
        #
        #  유효하지만 잘못 분류된 `REPORT` 가 실행 가능한 App-in-App 으로 만들어지면
        #  계약이 아예 없는 릴리스가 된다 — 그러면 아래 레거시 경로로 조용히 열린다.
        #  ⚠️ 그 앱은 계약도 승인도 없이 데이터를 만지고, 아무 오류도 나지 않는다.
        #  ★ 다만 **계약 이전에 만든 판**까지 막으면 기존 앱이 전부 멈춘다. 그래서
        #    경계는 릴리스가 들고 있는 `runtime_contract_profile` 이다(4c-0 과 같은 규칙).
        if release_contract_profile(release) and is_executable_app_in_app(release):
            return GateVerdict(
                ok=False, materialization_fingerprint=mat_fp,
                reasons=["실행 가능한 앱인데 승인된 런타임 계약이 없습니다 — "
                         "산출물 분류(`artifact_kind`)가 무엇이든, 사용자가 실행하는 "
                         "App-in-App 은 계약을 지나야 합니다."])
        #: 레거시(계약 이전) 릴리스는 그대로 연다 — 「없다」와 「어긋난다」는 다른 사실이다.
        return GateVerdict(ok=True, contract_fingerprint=NO_CONTRACT,
                           materialization_fingerprint=mat_fp, legacy=True)

    errs = arc.validate(contract)
    if errs:
        return GateVerdict(ok=False, materialization_fingerprint=mat_fp,
                           reasons=[f"계약을 읽을 수 없습니다: {errs[0]}"])
    if str((contract.get("approval") or {}).get("status", "")) != "APPROVED":
        return GateVerdict(ok=False, materialization_fingerprint=mat_fp,
                           reasons=["계약이 승인되지 않았습니다 — 승인 전 계약으로는 앱을 "
                                    "열 수 없습니다."])

    reasons = _compare(contract, bound)
    fp = contract_fingerprint(release)
    if reasons:
        return GateVerdict(ok=False, reasons=reasons, contract_fingerprint=fp,
                           materialization_fingerprint=mat_fp)
    #: ★ 데이터셋 0개는 정상이다 — 계약 0개 + 결속 0개면 여기까지 이유 없이 온다.
    return GateVerdict(ok=True, contract_fingerprint=fp, materialization_fingerprint=mat_fp)


def sealed_pair(release: Any, release_id: str) -> Tuple[str, str]:
    """요청마다 다시 계산하는 **지금의** 두 지문. 증명에 봉인된 값과 대조한다."""
    try:
        mat = app_data_service.materialization_fingerprint(str(release_id or "").strip())
    except Exception:
        mat = UNREADABLE
    return contract_fingerprint(release), mat
