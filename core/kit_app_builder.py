"""★★★ 키트 청사진 → **실제로 도는 앱.** (2026-08-23)

## 왜 이 파일이 생겼나

12분 여정의 「키트로 앱 생성·실행」 칸이 **한 번도 열린 적이 없었다.**

준비도 보드는 `app_blueprints` 를 읽어 「지금 만들 수 있는 것」을 그려 주지만, 그 옆에
**만드는 길이 없었다** — 프런트는 상태만 표시하고, 백엔드에는 청사진을 실체화하는
경로가 없었다.

⚠️⚠️ 그것이 이 저장소가 반복해서 잡아 온 고장의 한 종류다: **「보여 주는 것」과
  「되는 것」이 다르다.** 화면에 `READY` 가 떠도 누를 것이 없으면 그 화면은 사용자에게
  「내가 뭘 잘못했나」를 묻게 만든다.

## 이 파일이 하는 일과 하지 않는 일

    한다      청사진(app_id · name · datasets[계약키])을 **런타임 계약**으로 옮긴다
              준비도가 «만들 수 있다» 고 한 것만 만든다
              물질화는 기존 `contract_materializer` 에 맡긴다

    안 한다   스키마를 지어내기 · 준비도 판정 다시 하기 · 권한 판정(라우트의 일)

★ 실체화기는 이미 있었다. 없던 것은 **청사진에서 그것을 부르는 길**이다. 새 물질화기를
  만들지 않는다 — 두 벌이 되면 「어느 쪽이 진짜 앱인가」가 갈린다.

LLM 0콜.
"""
from __future__ import annotations

import logging
import re

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core import app_manifest
from core import app_runtime_contract as arc
from core import contract_materializer as cm
from core.data_preparation import readiness

_log = logging.getLogger(__name__)

#: 청사진이 요구하는 데이터는 **업무 데이터에서 읽는다.**
#: ⚠️ 다른 출처 의도를 쓰면 실체화기가 계약키를 무시하거나 거부한다 — 그 둘이 어긋나면
#:   「적혀 있으나 아무도 안 보는 계약키」가 생긴다.
SOURCE_INTENT = arc.ENTERPRISE_READ

#: 업무 데이터에서 읽는 데이터셋의 **역할.** 닫힌 목록(`app_data.DATA_ROLES`)의 값이다.
ENTERPRISE_ACTUAL = "ENTERPRISE_ACTUAL"


#: ★★★ **두 어휘를 잇는 명시 표.**
#:
#:   인증판 추론(`snapshot_service.infer_type`)  number · datetime · string · unknown
#:   앱 필드(`app_data.FIELD_TYPES`)             string · text · number · boolean · date
#:
#: ⚠️⚠️ 기본값으로 뭉개지 않는다. 「모르면 string」으로 두면 **날짜 열이 글자 열이 되고**
#:   화면에서 기간 필터가 조용히 안 먹는다 — 그리고 아무도 왜인지 모른다.
#: ⚠️ `unknown` 은 «값이 하나도 없는 열» 이다. 형을 정할 근거가 없으므로 `string` 으로
#:   두되, 그것이 **추정이 아니라 «관측된 값이 없다»** 라는 사실임을 여기 적어 둔다.
#: ★ 표에 없는 형이 오면 **막는다.** 새 형이 생겼는데 조용히 통과시키면 그 형은
#:   영영 잘못 저장된다.
FIELD_TYPE_MAP: Dict[str, str] = {
    "number": "number",
    #: ⚠️ 앱에는 `datetime` 이 없다. `date` 로 옮기면 **시각이 잘린다** — 그래서
    #:   시각까지 필요한 화면은 원본 판을 봐야 한다는 사실을 함께 남긴다.
    "datetime": "date",
    "string": "string",
    "unknown": "string",
}


class KitAppError(Exception):
    """앱을 만들지 못했다. ⚠️ 사유가 **반드시** 붙는다."""


def _keys(blueprint: Mapping[str, Any]) -> List[str]:
    return [str(k).strip() for k in (blueprint.get("datasets") or []) if str(k).strip()]


#: 데이터셋 런타임 이름의 문법. 정본 = `app_runtime_contract._DATASET_SCHEMA`.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

#: ★★★ **읽기 전용 업무 데이터의 중복입력 정책.**
#:   권위 원천(ERP)이 있으므로 «있으면 금지» 다 — 그것이 Zero Duplicate Entry Gate 의 뜻이다.
#: ⚠️ `NO_DUPLICATE_CHECK_REQUIRED` 도 검증은 통과하지만 **아무것도 막지 않는다.**
DUPLICATE_POLICY = "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS"

#: 필드 분류의 **선언 기본값**. ⚠️ 이것은 «평가» 가 아니라 «아직 평가하지 않았다» 다 —
#:   인증판은 분류를 들고 있지 않다. 개인정보·기밀 판정은 데이터 카탈로그가 붙여야 하고,
#:   붙기 전까지 `PUBLIC` 으로 두지 않는다(공개로 두면 되돌릴 수 없다).
DEFAULT_CLASSIFICATION = "INTERNAL"


def runtime_name(contract_key: str) -> str:
    """계약키 → 런타임 데이터셋 이름. `PRC-01` → `prc_01`.

    ⚠️⚠️ 종전에 계약키를 **그대로** 이름칸에 넣었다. 정본 스키마의 이름 문법
      (`^[a-z][a-z0-9_]{0,63}$`)에 맞지 않는 값이었는데, 실체화기가 `arc.validate()` 를
      부르지 않아 **끝까지 통과했다** — 스키마를 안 보고 내 말로 계약을 지은 결과다.
    ★ 계약키는 `enterprise_contract_key` 에 **그대로 남는다.** 한 칸에 둘을 섞지 않는다."""
    out = re.sub(r"[^a-z0-9_]", "_", str(contract_key).strip().lower()).strip("_")
    if out and out[0].isdigit():
        out = "k_" + out
    if not _NAME_RE.match(out):
        raise KitAppError(
            f"계약키 «{contract_key}» 를 데이터셋 이름으로 옮길 수 없습니다 — "
            f"이름 문법(^[a-z][a-z0-9_]{{0,63}}$)에 맞는 글자가 남지 않았습니다.")
    return out


def contract_from_blueprint(blueprint: Mapping[str, Any], *, project_id: str,
                            app_class: str, revision: int = 1,
                            schema_for: Optional[Any] = None,
                            labels: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """청사진 → **정본 스키마를 통과하는** 런타임 계약 초안.

    ★★★ 결과를 `arc.validate()` 로 **스스로 검사한다.** 검사하지 않으면 이 함수는
      「내 말로 쓴 계약」을 만들고, 그것이 물질화까지 통과한다 — 실제로 그랬다.

    ⚠️ 필드를 지어내지 않는다. `schema_for` 가 인증판에서 읽어 온다.
    ⚠️ `app_class` 에 기본값을 두지 않는다. `app_manifest` 가 「모르면 `departmental`
      로 두지 않고 비워 둔다 — 추측한 분류는 나중에 권한 판단의 근거로 쓰인다」라고
      적어 두었다. 부르는 쪽이 정해야 한다."""
    app_id = str(blueprint.get("app_id") or "").strip()
    if not app_id:
        raise KitAppError("청사진에 app_id 가 없습니다.")
    keys = _keys(blueprint)
    if not keys:
        #: ⚠️ 데이터 없는 앱을 만들면 화면은 열리는데 한 줄도 안 보인다 —
        #:   사용자는 그것을 「데이터가 없다」로 읽는다.
        raise KitAppError(f"{app_id}: 청사진에 데이터셋이 없습니다.")
    if not str(project_id or "").strip():
        raise KitAppError(f"{app_id}: 계약이 어느 프로젝트의 것인지 없습니다.")
    if str(app_class or "") not in app_manifest.APP_CLASSES:
        raise KitAppError(
            f"{app_id}: app_class 를 정해야 합니다 — 가능한 것은 "
            f"{list(app_manifest.APP_CLASSES)} 입니다(추측한 분류는 나중에 권한 판단의 "
            f"근거로 쓰입니다).")

    label_map = {k: str((v or {}).get("label") or "") if isinstance(v, Mapping) else str(v or "")
                 for k, v in (labels or {}).items()}

    datasets: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}
    for key in keys:
        name = runtime_name(key)
        if name in seen:
            #: ⚠️ 두 계약키가 같은 이름으로 접히면 런타임이 어느 쪽인지 모른다.
            raise KitAppError(
                f"{app_id}: «{seen[name]}» 와 «{key}» 가 같은 데이터셋 이름({name})으로 "
                f"접힙니다 — 런타임이 어느 쪽인지 알 수 없습니다.")
        seen[name] = key
        label = label_map.get(key) or key
        datasets.append({
            "name": name,
            "label": label,
            #: ★ 목적은 **이 계약이 하는 일의 사실 서술**이다. 업무상 목적을 지어내지
            #:   않는다 — 그것은 키트 manifest 가 말해야 하고, 지금은 말하지 않는다.
            "purpose": f"업무 데이터 «{key}»({label}) 를 읽어 «{app_id}» 화면에 보여 준다.",
            "allowed_actions": ["read"],
            "fields": _fields_for(key, schema_for),
            #: ★★★ 업무 데이터에서 읽는 것은 **회사 실적**이다.
            #: ⚠️ 종전에 내가 `"reference"` 라고 지어냈다 — 닫힌 목록에 없는 값이라
            #:   결속에서 막혔다. **지어낸 어휘는 반드시 어딘가에서 막힌다**
            #:   (막히지 않으면 더 나쁘다 — 뜻 없는 값이 저장된다).
            "data_role": ENTERPRISE_ACTUAL,
            "source_intent": SOURCE_INTENT,
            "duplicate_entry_policy": DUPLICATE_POLICY,
            "enterprise_contract_key": key,
        })

    contract: Dict[str, Any] = {
        "schema_version": arc.SCHEMA_VERSION,
        "contract_id": arc.contract_id_for(project_id, app_id),
        "revision": int(revision),
        "project_id": str(project_id).strip(),
        "task_id": app_id,
        "runtime_contract_version": arc.RUNTIME_CONTRACT_VERSION,
        #: ★★★ **초안이다. 승인이 아니다.**
        #:
        #: ⚠️⚠️ 여기서 `STATUS_APPROVED` 를 적으면 **요청자가 승인자 자리에 앉는다** —
        #:   이 저장소가 이미 한 번 잡은 결함이다(B2→G5). 승인 전 계약을 물질화하면
        #:   검토를 지나지 않은 권한이 DB 에 들어가고, 그 결속은 다음 단계에서
        #:   «정상» 으로 봉인된다.
        #: ★ 누르는 것은 사람이다. 빌더는 **누를 것을 만들 뿐**이다.
        "status": arc.STATUS_DRAFT,
        "app_class": str(app_class),
        #: ★ 능력 의도는 없다 — 이 앱은 업무 데이터를 **읽기만** 한다. 빈 목록은
        #:   「아직 안 적었다」가 아니라 「요구한 것이 없다」다.
        "capability_intents": [],
        #: ★★★ manifest 를 **손으로 짓지 않는다.** `app_manifest.build()` 가 정본이다 —
        #:   고정값(인증 상속·회사 문맥·플랫폼 감사·금지 기능)을 호출자가 바꿀 수 없게
        #:   막고, 평면·구조화 두 표현을 **한 곳에서** 만든다.
        #: ⚠️⚠️ 처음에 내가 네 칸을 손으로 적었다가 `version` 누락과 두 표현 불일치로
        #:   막혔다. 상수를 베끼는 것도 «지어내기» 다 — 플랫폼이 규칙을 바꾸면 이 계약만
        #:   옛 값을 들고 남는다.
        #: ★ 능력은 계약의 `allowed_actions` 에서 **파생**한다. 손으로 적으면 manifest 가
        #:   계약을 벗어나고, 그때 계약은 설명서가 된다(`_manifest_contract_mismatch`).
        "manifest": app_manifest.build(
            capabilities=[{"resource": d["name"], "actions": d["allowed_actions"]}
                          for d in datasets],
            app_class=str(app_class)),
        "datasets": datasets,
        "unsupported_requirements": [],
        "semantic_fingerprint": "",
        #: ★ 승인 봉투는 **비워서 만든다.** `PENDING` 은 「사람이 아직 안 봤다」다.
        "approval": {"status": "PENDING"},
    }
    contract["semantic_fingerprint"] = arc.semantic_fingerprint(contract)

    #: ★★★ **스스로 검사한다.** 여기서 안 보면 다음에 보는 곳은 없다 —
    #:   실체화기는 `status` 만 보고 스키마는 보지 않는다(실측 확인).
    errs = arc.validate(contract)
    if errs:
        raise KitAppError(f"{app_id}: 만든 계약이 정본 스키마를 통과하지 못합니다 — "
                          + " / ".join(errs[:4]))
    return contract


def _fields_for(key: str, schema_for: Optional[Any]) -> List[Dict[str, Any]]:
    """계약 필드 목록. **인증판에서 온 것만** 담는다."""
    out: List[Dict[str, Any]] = []
    for f in (list(schema_for(key)) if schema_for else []):
        name = str(f.get("name", ""))
        if not _NAME_RE.match(name):
            #: ⚠️ 조용히 고쳐 넣지 않는다. 이름을 바꾸면 **계약의 칸과 실제 자료의 칸이
            #:   갈라지고**, 화면은 늘 비어 있는 칸을 그린다.
            raise KitAppError(
                f"{key}.{name or '(이름 없음)'}: 필드 이름이 문법에 맞지 않습니다 "
                f"(^[a-z][a-z0-9_]{{0,63}}$) — 인증 단계에서 열 이름을 고쳐야 합니다.")
        out.append({
            "name": name, "type": str(f.get("type", "string")),
            #: ⚠️ 인증판은 「필수인가」를 말하지 않는다. `True` 로 두면 값이 빈 행이
            #:   전부 거부되고, 그것은 **원천에 있는 사실을 우리가 지우는 일**이다.
            "required": False,
            "classification": DEFAULT_CLASSIFICATION,
        })
    return out


def fields_from_certified(store: Any, instance_id: str, contract_key: str) -> List[dict]:
    """필드를 **인증판에서 읽는다.** 없으면 빈 목록.

    ★★★ 스키마를 지어내지 않는다는 원칙의 **실행**이다. 필드는 인증 시점에 원문에서
      추론돼 `dataset_snapshots.schema_json` 에 봉인돼 있다 — 그것을 그대로 쓴다.
    ⚠️ 손으로 적으면 계약과 실제 자료가 갈라지고, 화면은 **있지도 않은 칸**을 그린다.
    ⚠️ 인증되지 않은 판의 스키마는 쓰지 않는다 — 검토를 지나지 않은 모양이다."""
    from core.data_preparation import readiness as rd

    rows = [r for r in (store.list_snapshots(instance_id) or [])
            if str(r.get("dataset_contract_key") or "") == contract_key]
    latest = rd.latest_certified(rows)
    if not latest:
        return []
    from core.data_preparation import usage_policy
    try:
        usage_policy.require_usable(store, latest)
    except usage_policy.UsageHoldError as exc:
        raise KitAppError(str(exc)) from exc
    raw = latest.get("schema")
    if raw is None:
        import json as _json
        try:
            raw = _json.loads(latest.get("schema_json") or "[]")
        except Exception:
            return []
    if isinstance(raw, dict):
        raw = raw.get("fields") or []

    #: ★★★ **플랫폼 예약 이름은 앱 필드가 될 수 없다.**
    #:
    #: ⚠️⚠️ `record_id`·`created_at` 같은 이름은 레코드가 이미 갖는 항목이다. 앱이 같은
    #:   이름을 쓰면 **「누가 언제 만들었나」를 앱이 덮어쓸 수 있다**(감사 표시 위조).
    #:   그래서 `app_data` 가 거부한다 — 옳은 거부다.
    #: ★ 업무 CSV 는 그 이름들을 **봉투 칸**으로 쓴다(`record_id` …). 앱 필드로 옮길
    #:   때는 봉투를 벗긴다.
    #: ⚠️ 말없이 버리지 않는다 — 무엇을 뺐는지 남긴다. 조용히 빼면 「왜 그 칸이 화면에
    #:   없나」에 아무도 답할 수 없다.
    from core.app_data import RESERVED_FIELD_NAMES

    kept, dropped = [], []
    for f in (raw or []):
        name = str(f.get("name", "")).strip()
        if not name:
            continue
        if name in RESERVED_FIELD_NAMES:
            dropped.append(name)
            continue
        raw_type = str(f.get("type", "") or "unknown")
        mapped = FIELD_TYPE_MAP.get(raw_type)
        if mapped is None:
            #: ⚠️ 모르는 형을 `string` 으로 떨어뜨리지 않는다 — 그 열은 영영 잘못 저장된다.
            raise KitAppError(
                f"{contract_key}.{name}: 앱 필드로 옮길 수 없는 형입니다({raw_type}) — "
                f"변환 표에 넣고 무엇으로 옮길지 정해야 합니다.")
        kept.append({"name": name, "type": mapped})
    if dropped:
        #: ★ 남기되 **표준출력을 더럽히지 않는다.** `print` 는 회귀 출력에 열 줄씩 쌓여
        #:   진짜 실패를 가린다 — 기록의 목적은 「나중에 답할 수 있게」이지 지금 시끄럽게가
        #:   아니다.
        _log.info("%s: 플랫폼 예약 칸 %d개를 앱 필드에서 제외했습니다 — %s",
                  contract_key, len(dropped), sorted(dropped))
    return kept


def release_id_for(instance_id: str, app_id: str) -> str:
    """이 인스턴스의 이 앱이 쓰는 릴리스 식별자.

    ★ 결정론적이다 — 같은 인스턴스·같은 앱을 다시 만들면 **같은 자리를 이어받는다**
      (`adopt_dataset`). 새로 만들면 현업이 쌓은 레코드가 승계되지 않는다."""
    return f"kitapp_{str(instance_id).strip()}_{str(app_id).strip()}"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _owner_dept_of(scope_node_id: str) -> str:
    """이 조직 범위를 **소유한 부서**. 못 찾으면 빈 문자열.

    ⚠️ 지어내지 않는다. 비면 `app_policy._scope_ok` 가 부서 권한 축에서 막고, 그것이
      맞다 — 「소유자를 모르는 앱」을 열어 두면 누구 것인지 모르는 화면이 생긴다."""
    try:
        from core.org_directory import org_directory
        want = str(scope_node_id or "").strip()
        for d in org_directory.list_departments():
            if str(d.get("scope_node_id") or "").strip() == want:
                return str(d.get("dept_id") or "")
    except Exception:                                # pragma: no cover - 조직 조회 실패
        return ""
    return ""


def publish_release(*, release_id: str, app_id: str, name: str, instance_id: str,
                    contract: Mapping[str, Any], tenant_id: str, scope_node_id: str,
                    entity_mode: str, actor_id: str, created_at: str) -> Dict[str, Any]:
    """앱을 **열 수 있게** 릴리스를 게시한다.

    ## ⚠️⚠️ 이것이 없으면 「만들었다」와 「쓸 수 있다」가 갈린다 (2026-08-24 실측)

    빌더는 데이터셋 6종을 실제로 물질화했고 목록도 「결속 6」이라고 표시했다. 그런데
    앱을 여는 `/api/v1/appdata/datasets?release_id=…` 는 **404** 였다:
    「지금 선택한 회사·실행 문맥의 자료가 아닙니다.」

    원인은 권한이 아니라 **릴리스 기록이 아예 없던 것**이다. `app_data_control.
    _release_scope()` 는 `library/<release_id>/release.json` 에서 테넌트·실행모드·
    조직범위를 읽는데, 파일이 없으면 `INVALID` 로 떨어지고 PDP 는 fail-closed 다.
    막힌 이유가 맞는 자리에서 나오지 않아 「권한 문제」로 보였다.

    ★★★ **물질화보다 먼저** 부른다 — 물질화가 `release_id` 로 릴리스를 읽어 테넌트·앱을
      확인한다(`factory_control` 이 같은 이유로 같은 순서를 쓴다).
    ★ 소유 미러(`ownership`)도 함께 적는다. `_release_scope` 는 소유 축을 미러에서
      읽고, 없으면 파일 값으로 떨어진다 — 둘을 같은 값으로 둔다.
    """
    import json
    import os

    from core import library_paths

    owner_dept = _owner_dept_of(scope_node_id)
    release = {
        #: ★ 이 릴리스가 **키트 앱**임을 적는다 — 공장 프로젝트 릴리스와 모양이 다르고,
        #:   구분이 없으면 승격·삭제 같은 절차가 남의 것에 손댄다.
        "kind": "kit_app",
        #: ★★★ 업무 키트 앱은 별도 소스코드를 생성하지 않고 호스트가 계약을 렌더링한다.
        #:
        #: ⚠️ 이것은 정적 검사 면제 표식이 아니다. 승격기는 코드가 0개일 때 이 값을 본 뒤
        #:   아래 Manifest를 현재 규칙으로 다시 검증하고, 내용 지문과 승인 계약의 Manifest까지
        #:   모두 대조한다. 소스 파일이 생기면 이 표식과 무관하게 기존 스캐너가 그 파일을 본다.
        "execution_surface": "HOST_DECLARATIVE",
        "release_id": release_id,
        "app_id": app_id,
        "name": name,
        "instance_id": instance_id,
        #: ★★★ **승인된 계약을 릴리스에 봉인한다.**
        #:
        #: ⚠️ `app_contract_gate.release_contract()` 는 `runtime_contract` 키만 읽는다.
        #:   비어 있으면 승격 검사의 「계약↔물질화 대조」가 «계약 없는 판» 으로 판정하고,
        #:   `app_data_runtime` 의 발급 게이트도 같은 자리에서 막힌다.
        #: ★ 정본은 `kit_app_contracts` 표지만, **이 릴리스가 실제로 쓴 판**은 여기다 —
        #:   나중에 계약이 개정돼도 「이 판이 무엇으로 만들어졌나」가 흔들리지 않는다.
        "runtime_contract": dict(contract),
        #: ★★★ **매니페스트 스냅샷.** `app_proof.app_facts()` 가 여기서 「이 앱이 하겠다고
        #:   선언한 것」을 읽고, `grantable_actions()` 가 그것과 사용자 권한의 **교집합**을
        #:   증명에 담는다.
        #: ⚠️⚠️ 없으면 선언이 빈 집합이라 교집합도 비고, 증명 발급이 **404** 다 —
        #:   그리고 그 404 는 「릴리스가 없다」와 구분되지 않아 원인을 가리지 못한다
        #:   (2026-08-24 실측: 승격까지 200 인데 앱은 여전히 안 열렸다).
        #: ★ 계약이 이미 매니페스트를 갖고 있다 — 지어내지 않고 그것을 봉인한다.
        "manifest": app_manifest.snapshot(contract.get("manifest") or {}),
        "app_class": str(contract.get("app_class") or ""),
        "kit_app_contract_id": str(contract.get("contract_id") or ""),
        "kit_app_revision": int(contract.get("revision") or 1),
        "semantic_fingerprint": str(contract.get("semantic_fingerprint") or ""),
        #: 문맥 — `app_policy._ctx_ok` 가 이 셋을 본다. 하나라도 비면 fail-closed 다.
        "tenant_id": str(tenant_id or ""),
        "entity_mode": str(entity_mode or ""),
        "enterprise_scope_id": str(scope_node_id or ""),
        "owner_dept_id": owner_dept,
        "owner_user_id": "",
        "created_by": str(actor_id or ""),
        "created_at": created_at,
        #: ★★★ **`project_id` 는 이 릴리스의 «앱 정체»다** — 공장 프로젝트 id 가 아니다.
        #:   `app_data.release_identity()` 가 `(tenant_id, project_id)` 를 «앱» 으로 읽고,
        #:   `adopt_dataset()` 이 그 정체로 **기존 데이터셋을 이어받을지**를 정한다.
        #:
        #: ⚠️⚠️ 처음엔 「키트 앱은 공장 프로젝트가 아니다」며 비워 뒀다. 그러자 정체를
        #:   못 읽어 승계가 끊겼고, 「앱 만들기」를 **두 번째 누르면 500** 이었다
        #:   (「같은 이름의 데이터셋이 이미 있습니다: inv_02」). 개정할 때마다 현업이
        #:   쌓은 레코드가 승계되지 않는 것도 같은 자리다.
        #: ★ 값은 `release_id` 다 — 승계 범위를 **이 인스턴스의 이 앱**으로 정확히 묶는다.
        #:   다른 인스턴스는 다른 회사·다른 범위이므로 이어받으면 안 된다.
        "project_id": release_id,
        "not_for_management_decision": bool(
            str(entity_mode or "").upper() != "REAL"),
    }
    if contract.get("schema_version") == "2.0":
        release["runtime_document_version"] = "2.0"
        release["not_for_management_decision"] = release["not_for_management_decision"] or any(
            ref["certification_state"] == "DEMO_CERTIFIED" or ref.get("certified_use_kind") == "OPERATIONAL"
            for ref in contract["process_context"]["verified_binding_refs"])
    rel_dir = library_paths.release_dir(release_id)
    os.makedirs(rel_dir, exist_ok=True)
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as fh:
        json.dump(release, fh, ensure_ascii=False, indent=2)

    if owner_dept:
        try:
            from core.org_directory import org_directory
            org_directory.set_ownership("release", release_id, dept_id=owner_dept,
                                        visibility="dept")
        except Exception:                            # pragma: no cover - 미러 기록 실패
            #: ⚠️ 미러가 없어도 파일 값으로 판정된다 — 조용히 넘어가되 지어내지 않는다.
            _log.warning("릴리스 소유 미러를 적지 못했습니다: %s", release_id)

    #: ★★★ **후보 판으로 기록한다.** 물질화는 시연 평면에 하므로 청중도 Preview 여야
    #:   한다(`app_preview.audience_for_state`).
    #:
    #: ⚠️⚠️ 기록하지 않으면 `program_lifecycle.get_status()` 가 「미기록 → active」로
    #:   답하고, 청중이 **operational** 로 유도된다. 그러면 읽기는 운영 평면을 보고
    #:   자료는 시연 평면에 있어 **200 인데 0건**이 된다 — 「비었다」로 보이지만 실제로는
    #:   다른 서랍을 연 것이다(2026-08-24 실측).
    #: ★ 운영 평면으로 올리는 것은 **승격의 일**이다(`factory_control` 의 승격 경로).
    try:
        from core.program_lifecycle import CANDIDATE, program_lifecycle
        if str(program_lifecycle.get_status(release_id).get("status") or "") != CANDIDATE:
            program_lifecycle.set_status(
                release_id, CANDIDATE, actor=str(actor_id or ""),
                reason="업무 키트 앱 — 시연 평면 후보 판(승격 전)")
    except Exception as exc:                         # pragma: no cover - 기록 실패
        #: ⚠️ 조용히 넘어가지 않는다. 기록이 없으면 앱은 만들어져도 **열리지 않는다.**
        raise KitAppError(
            f"{app_id}: 릴리스를 후보 판으로 기록하지 못했습니다({exc}) — 기록이 "
            f"없으면 앱이 만들어져도 열리지 않습니다.") from exc
    return release


def _output_row(outputs: Sequence[Mapping[str, Any]], app_id: str,
                name: str) -> Optional[Mapping[str, Any]]:
    """준비도 판정에서 이 앱의 줄을 찾는다.

    ⚠️ 준비도는 산출물을 **이름**으로 적는다. `app_id` 로도 이름으로도 찾아 본다 —
      못 찾으면 `None` 이고, 호출부가 그것을 «막힘» 으로 다룬다(찾지 못한 것을
      «괜찮음» 으로 읽지 않는다)."""
    for row in outputs or []:
        label = str(row.get("output") or "").strip()
        if label and label in (app_id, name):
            return row
    return None


def build(*, blueprint: Mapping[str, Any], instance_id: str, outputs: Sequence[Mapping[str, Any]],
          actor_id: str, store: Any, app_data: Any,
          tenant_id: str, scope_node_id: str, entity_mode: str,
          approved_contract: Optional[Mapping[str, Any]] = None,
          revision: int = 1, context: Optional[Mapping[str, Any]] = None,
          repo: Any = None) -> Dict[str, Any]:
    """청사진 하나를 실제 앱으로 만든다.

    ★★★ **준비도가 «만들 수 있다» 고 한 것만 만든다.** 판정은 여기서 다시 하지 않고
      `readiness.evaluate_outputs()` 의 결과를 받는다 — 두 곳에서 판정하면 규칙이
      갈라지고, 갈라진 규칙은 언젠가 한쪽만 고쳐진다.

    ⚠️⚠️ 막힌 산출물을 만들지 않는다. 「일부 데이터로라도 열어 주자」가 위험하다 —
      열린 앱은 **빈 화면**을 보여 주고, 사용자는 그것을 「우리 회사에 자료가 없다」로
      읽는다. 실제로는 우리가 아직 준비하지 못한 것이다.

    ⚠️ 부분 물질화도 없다. 실체화기가 `plan()` 으로 전부 해석한 뒤에야 쓴다 —
      중간에 실패하면 아무것도 만들어지지 않는다."""
    if isinstance(approved_contract, Mapping) and approved_contract.get("schema_version") == "2.0":
        return build_v2(store=store, app_data=app_data, instance_id=instance_id,
                        app_id=str(blueprint.get("app_id") or ""), actor_id=actor_id,
                        context=context, revision=approved_contract.get("revision"),
                        expected_fingerprint=approved_contract.get("semantic_fingerprint"), repo=repo)
    app_id = str(blueprint.get("app_id") or "").strip()
    name = str(blueprint.get("name") or app_id)
    if not str(instance_id or "").strip():
        raise KitAppError("어느 인스턴스의 앱인지 없습니다.")
    if not str(actor_id or "").strip():
        #: ⚠️ 누가 만들었는지 없으면 나중에 「이 앱은 왜 있나」에 답할 수 없다.
        raise KitAppError("만든 사람이 필요합니다.")

    row = _output_row(outputs, app_id, name)
    if row is None:
        raise KitAppError(
            f"{app_id}: 준비도 판정에 이 산출물이 없습니다 — 만들 수 있는지 "
            f"확인하지 못했습니다.")
    state = str(row.get("state") or "")
    if state == readiness.BLOCKED_OUTPUT:
        #: ★ 준비도가 이미 사람이 읽을 사유와 다음 행동을 만들어 두었다. 그대로 전한다 —
        #:   여기서 새 문구를 지으면 같은 사실이 두 가지로 설명된다.
        raise KitAppError(
            f"{row.get('user_message') or '아직 만들 수 없습니다.'} "
            f"다음 할 일: {row.get('next_action') or '관리자에게 문의하십시오.'}")
    if state not in (readiness.AVAILABLE, readiness.AVAILABLE_WITH_WARNING):
        raise KitAppError(f"{app_id}: 알 수 없는 준비도 상태입니다({state or '없음'}).")

    #: ★★★ 계약은 **밖에서 승인된 것**만 받는다.
    #:
    #: ⚠️⚠️ 종전에는 안 주면 여기서 초안을 만들었다. 어차피 바로 아래에서 거부할 것을
    #:   만드느라 **저장소를 읽었고**, 승인 이전 단계에서 저장소가 필요해졌다.
    #:   초안 작성은 승인 절차의 일이지 물질화의 일이 아니다 —
    #:   `contract_from_blueprint()` 를 따로 부른다.
    if not approved_contract:
        raise KitAppError(
            f"{app_id}: 승인된 앱 계약이 없습니다 — 계약을 만들어 승인을 받은 뒤에 "
            f"만들 수 있습니다.")
    contract = dict(approved_contract)
    status = str(contract.get("status") or "")
    if status != arc.STATUS_APPROVED:
        #: ⚠️ 여기서 상태를 올리지 않는다. 올리면 승인 절차가 **이름만 남는다.**
        raise KitAppError(
            f"{app_id}: 앱 계약이 아직 승인되지 않았습니다"
            f"(현재 {arc.STATUS_LABEL.get(status, status or '없음')}) — "
            f"승인 뒤에 만들 수 있습니다.")
    reject_process_legacy(store, instance_id)
    release_id = release_id_for(instance_id, app_id)
    #: ★★★ **릴리스를 먼저 게시한다.** 없으면 만들어져도 열리지 않는다(위 주석 참조).
    published = publish_release(
        release_id=release_id, app_id=app_id, name=name, instance_id=instance_id,
        contract=contract, tenant_id=tenant_id, scope_node_id=scope_node_id,
        entity_mode=entity_mode, actor_id=actor_id, created_at=_now_iso())
    try:
        out = cm.materialize(contract, release_id=release_id, actor_id=actor_id,
                             store=store, app_data=app_data, tenant_id=tenant_id,
                             scope_node_id=scope_node_id, entity_mode=entity_mode)
    except cm.MaterializeError as exc:
        #: ⚠️ 실체화 실패를 «만들었는데 비었다» 로 접지 않는다. 그 사유가 사람이 고칠
        #:   유일한 실마리다.
        raise KitAppError(f"{app_id}: {exc}") from exc

    return {
        "app_id": app_id, "name": name, "release_id": release_id,
        "instance_id": str(instance_id).strip(),
        "state": state,
        #: ★ 무엇이 만들어졌는지 이름으로 돌려준다 — 「만들었다」만 말하면 확인할 수 없다.
        "datasets": [str(d.get("name", "")) for d in (out.datasets or [])],
        "required_datasets": _keys(blueprint),
        #: ★ 열 수 있는 상태인지 화면이 바로 알 수 있게 — 소유 부서가 비면 못 연다.
        "owner_dept_id": str(published.get("owner_dept_id") or ""),
        "warning": str(row.get("user_message") or "") if state == readiness.AVAILABLE_WITH_WARNING else "",
    }


def reject_process_legacy(store, instance_id):
    """B2 적용본은 서버 소유 sidecar로 판단한다. 요청한 schema가 cohort가 아니다."""
    from core.data_preparation.process_kit_instances import binding_for_instance
    from core.enterprise_context.process_schema import ProcessError
    # DB 없는 순수 1.0 빌더 대역은 기존 물질화 계층이 맡는다. 실제 저장소에는 항상
    # get_instance가 있으며 그 경우 sidecar 조회 실패를 legacy로 폴백하지 않는다.
    if not callable(getattr(store, "get_instance", None)):
        return
    instance = store.get_instance(instance_id)
    if instance and binding_for_instance(store, instance):
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "새 업무 팩 적용본에는 2.0 고정 업무 문맥이 필요합니다.", 409)


def pinned_blueprint(bundle, app_id):
    from core.enterprise_context.process_schema import ProcessError
    rows = [b for b in bundle["blueprints"]["blueprints"] if b["app_id"] == app_id]
    if len(rows) != 1:
        raise ProcessError("PROCESS_BLUEPRINT_NOT_FOUND", "고정 팩의 앱 후보를 찾을 수 없습니다.", 404)
    return dict(rows[0])


def _fixed_schema(conn, ref):
    """이미 검증한 정확 snapshot의 열만 변환한다. 최신 인증판/빈 schema 폴백 없음."""
    import json
    from core.app_data import RESERVED_FIELD_NAMES
    from core.enterprise_context.process_context import snapshot_fingerprint
    from core.enterprise_context.process_schema import ProcessError
    raw = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (ref["snapshot_id"],)).fetchone()
    if raw is None or snapshot_fingerprint(dict(raw)) != ref["snapshot_fingerprint"]:
        raise ProcessError("PROCESS_BINDING_CONFLICT", "고정 인증판이 변경되었습니다.", 409)
    try:
        schema = json.loads(raw["schema_json"])
        if isinstance(schema, dict):
            schema = schema["fields"]
        if not isinstance(schema, list) or not schema:
            raise ValueError("schema required")
        fields, seen = [], set()
        for field in schema:
            name, kind = field["name"], field["type"]
            if name in seen or not isinstance(name, str):
                raise ValueError("duplicate field")
            seen.add(name)
            if name in RESERVED_FIELD_NAMES:
                continue
            if kind not in FIELD_TYPE_MAP or not _NAME_RE.fullmatch(name):
                raise ValueError("unsupported field")
            fields.append({"name": name, "type": FIELD_TYPE_MAP[kind]})
        if not fields:
            raise ValueError("no usable fields")
        return fields
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcessError("PROCESS_SCHEMA_UNAVAILABLE", "고정 인증판의 데이터 열 형식을 확인하지 못했습니다.", 503) from exc


def contract_from_process_context(store, *, instance_id, app_id, actor_id, context,
                                  process_context, app_class, revision=1, repo=None):
    """서버 pinned 후보 + 고정 인증 schema → 2.0 초안. 도메인 승인/자동 실행 아님."""
    return _contract_from_process_context(store, instance_id=instance_id, app_id=app_id,
        actor_id=actor_id, context=context, process_context=process_context, app_class=app_class,
        revision=revision, repo=repo, for_action="GENERATE")


def _contract_from_process_context(store, *, instance_id, app_id, actor_id, context,
                                   process_context, app_class, revision, repo, for_action):
    """생산자는 GENERATE, 고정 승인 원문 재검증은 실제 소비 action을 유지한다."""
    import copy
    from core import project_data_context as pdc
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_schema import ProcessError
    if type(revision) is not int or revision < 1:
        raise ProcessError("PROCESS_CONTRACT_INVALID", "양의 정수 개정이 필요합니다.", 422)
    instance, bundle, verified = pdc.process_instance(store, instance_id, actor_id=actor_id,
        context=context, process_context=process_context, repo=repo, for_action=for_action)
    # 승인 검토는 RELEASE/GENERATE 권한을 발급받는 일이 아니다. 다만 READ로
    # 현재 문맥을 검증했더라도 인증 데이터가 준비되지 않은 계약은 만들지 않는다.
    from core.enterprise_context.process_context import DATA_ACTIONS
    for blocker in verified["blockers"]:
        if blocker["reason_code"] != "PROCESS_ACTION_FORBIDDEN" and set(blocker["blocking_actions"]) & set(DATA_ACTIONS):
            raise ProcessError(blocker["reason_code"], "현재 인증 데이터 근거를 확인하십시오.", 409)
    blueprint = pinned_blueprint(bundle, app_id)
    from core.enterprise_context.process_schema import ProcessBoundary
    resolved = ProcessContextService(repo=repo, store=store).configuration.resolved(
        boundary=ProcessBoundary.model_validate(verified["context_key"]), actor=actor_id, context=context,
        profile_id=verified["profile_id"])
    suggestions = {b["app_id"] for b in resolved["payload"]["bindings"]
                   if b["kind"] == "BLUEPRINT_SUGGESTION" and b["process_id"] in verified["process_ids"]
                   and b["kit_id"] == bundle["kit_id"] and b["kit_version"] == bundle["version"]}
    if app_id not in suggestions:
        raise ProcessError("PROCESS_BLUEPRINT_PROCESS_MISMATCH", "선택 업무의 고정 앱 후보가 아닙니다.", 409)
    refs = pdc.process_refs_for_instance(verified, instance_id)
    keys = _keys(blueprint)
    if not keys or len(set(keys)) != len(keys) or set(keys) - set(refs):
        raise ProcessError("PROCESS_BLUEPRINT_REQUIREMENTS_UNRESOLVED", "앱 후보가 요구한 고정 데이터 참조를 모두 준비하십시오.", 409)
    with ProcessContextService._errors():
        with store.transaction() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            pdc.check_process_refs_conn(conn, store=store, instance=instance, bundle=bundle,
                process_context=verified, actor_id=actor_id, context=context, repo=repo)
            schemas = {key: _fixed_schema(conn, refs[key]) for key in keys}
    labels = {d["dataset_contract_key"]: d.get("label", d["dataset_contract_key"]) for d in bundle["profile"]["datasets"]}
    try:
        contract = contract_from_blueprint(blueprint, project_id=instance_id, app_class=app_class,
            revision=revision, labels=labels, schema_for=lambda key: schemas[key])
    except KitAppError as exc:
        raise ProcessError("PROCESS_CONTRACT_INVALID", "앱 후보 분류·필드 계약을 확인하십시오.", 422) from exc
    contract["schema_version"] = "2.0"
    contract["process_context"] = copy.deepcopy(verified)
    # 1.0 함수/출력은 그대로 둔다. 2.0 목적에 표시 label을 삽입하면 이름만 바꿔도
    # 의미 지문이 바뀌므로 안정 계약키와 앱 식별자만 사용한다.
    for dataset in contract["datasets"]:
        dataset["purpose"] = f"업무 데이터 «{dataset['enterprise_contract_key']}»를 «{app_id}»에서 읽는다."
    contract["semantic_fingerprint"] = arc.semantic_fingerprint(contract)
    errors = arc.validate(contract)
    if errors:
        raise ProcessError("PROCESS_CONTRACT_INVALID", "생성한 2.0 계약의 형식을 확인하십시오.", 422)
    return contract


def build_v2(*, store, app_data, instance_id, app_id, revision, expected_fingerprint,
             actor_id, context, repo=None):
    """실제 DB의 승인 계약만 게시/물질화한다. 호출자가 준 READY나 승인 본문은 안 쓴다."""
    from core import kit_app_contract as kac, project_data_context as pdc
    from core.enterprise_context.process_schema import ProcessError
    row = kac.validated_v2(store, instance_id=instance_id, app_id=app_id, revision=revision,
        expected_fingerprint=expected_fingerprint, actor_id=actor_id, context=context,
        for_action="GENERATE", require_approved=True, repo=repo)
    contract = row["contract"]
    instance, bundle, _ = pdc.process_instance(store, instance_id, actor_id=actor_id, context=context,
        process_context=contract["process_context"], for_action="GENERATE", repo=repo)
    blueprint = pinned_blueprint(bundle, app_id)
    try:
        cm.plan(contract, store=store, tenant_id=instance["tenant_id"], scope_node_id=instance["scope_node_id"],
                entity_mode=instance["entity_mode"])
    except cm.MaterializeError as exc:
        raise ProcessError("PROCESS_MATERIALIZATION_CONFLICT", "고정 계약 물질화 계획을 확인하십시오.", 409) from exc
    # plan 뒤에도 현재 게이트를 통과해야 한다. FS·DP는 분산 원자적이라고 주장하지 않는다.
    kac.validated_v2(store, instance_id=instance_id, app_id=app_id, revision=revision,
        expected_fingerprint=expected_fingerprint, actor_id=actor_id, context=context,
        for_action="GENERATE", require_approved=True, repo=repo)
    release_id = release_id_for(instance_id, app_id)
    from core.studio_release_cohort import pin_release_cohort
    pin_release_cohort(store, release_id=release_id, instance_id=instance_id, app_id=app_id,
                       context_key=contract["process_context"]["context_key"])
    _verify_cohort_v2(store, contract, instance_id, release_id, app_id)
    try:
        published = publish_release(release_id=release_id, app_id=app_id, name=blueprint["name"],
            instance_id=instance_id, contract=contract, tenant_id=instance["tenant_id"], scope_node_id=instance["scope_node_id"],
            entity_mode=instance["entity_mode"], actor_id=actor_id, created_at=_now_iso())
    except (KitAppError, OSError) as exc:
        raise ProcessError("PROCESS_RELEASE_WRITE_UNAVAILABLE", "후보 릴리스 저장을 완료하지 못했습니다.", 503) from exc
    _verify_published_v2(published, contract, instance, release_id, app_id)
    _verify_cohort_v2(store, contract, instance_id, release_id, app_id)
    try:
        out = cm.materialize(contract, release_id=release_id, actor_id=actor_id, store=store, app_data=app_data,
            tenant_id=instance["tenant_id"], scope_node_id=instance["scope_node_id"], entity_mode=instance["entity_mode"])
    except cm.MaterializeError as exc:
        raise ProcessError("PROCESS_MATERIALIZATION_CONFLICT", "고정 계약 물질화를 완료하지 못했습니다.", 409) from exc
    expected_names = {dataset["name"] for dataset in contract["datasets"]}
    if ({dataset.get("name") for dataset in out.datasets} != expected_names or len(out.datasets) != len(expected_names)
            or any(dataset.get("release_id") != release_id for dataset in out.datasets)):
        raise ProcessError("PROCESS_MATERIALIZATION_UNAVAILABLE", "물질화 결과의 데이터셋·릴리스 정체성이 다릅니다.", 503)
    return dict(app_id=app_id, name=blueprint["name"], release_id=release_id, instance_id=instance_id,
                state=readiness.AVAILABLE, datasets=[d["name"] for d in out.datasets], required_datasets=_keys(blueprint),
                owner_dept_id=published.get("owner_dept_id", ""), warning="", runtime_document_version="2.0")


def _verify_published_v2(published, contract, instance, release_id, app_id):
    """publish 반환값뿐 아니라 저장된 후보 release/manifest/계약을 read-back한다."""
    import json
    from pathlib import Path
    from core import library_paths
    from core.enterprise_context.process_schema import ProcessError
    expected = {"release_id": release_id, "project_id": release_id, "app_id": app_id,
                "instance_id": instance["instance_id"], "tenant_id": instance["tenant_id"],
                "entity_mode": instance["entity_mode"], "enterprise_scope_id": instance["scope_node_id"],
                "runtime_document_version": "2.0",
                "runtime_contract": contract, "manifest": app_manifest.snapshot(contract["manifest"])}
    try:
        with (Path(library_paths.release_dir(release_id)) / "release.json").open(encoding="utf-8") as stream:
            stored = json.load(stream)
        if any(stored.get(k) != v or published.get(k) != v for k, v in expected.items()):
            raise ValueError("release readback mismatch")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ProcessError("PROCESS_RELEASE_WRITE_UNAVAILABLE", "후보 릴리스·manifest·고정 계약 저장을 확인하지 못했습니다.", 503) from exc


def _verify_cohort_v2(store, contract, instance_id, release_id, app_id):
    from core.studio_release_cohort import get_release_cohort
    from core.enterprise_context.process_schema import ProcessError
    expected = dict(release_id=release_id, instance_id=instance_id, app_id=app_id,
                    context_key=contract["process_context"]["context_key"], runtime_document_version="2.0")
    cohort = get_release_cohort(store, release_id)
    if not isinstance(cohort, Mapping) or any(cohort.get(k) != v for k, v in expected.items()):
        raise ProcessError("PROCESS_RELEASE_COHORT_UNAVAILABLE", "서버 릴리스 cohort 저장을 확인하지 못했습니다.", 503)
