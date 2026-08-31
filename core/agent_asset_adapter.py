"""[P1-2] 기존 **파일 자산**을 범위형 저장소와 같은 모양으로 노출하는 어댑터.

## 왜 어댑터인가 — 파일을 DB 로 옮기지 않는 이유

지금 에이전트·워크플로우·스킬은 파일에 있고 **그 파일로 실제 파이프라인이 돌고 있다.**
한 번에 DB 로 이관하면 이관이 끝나는 순간까지 시스템이 멈추거나, 이관 중 실패하면 «돌던 것이
안 되는» 상태가 된다. 그래서 P1-2 는 **읽는 모양만 통일**한다:

  · 파일은 그대로 두고 종전 경로(`core.agent_registry`)가 계속 쓰기를 담당한다.
  · 조회는 `agent_assets.AgentAssetStore.get()` 과 **같은 dict 모양**으로 준다.
  · 그래서 P1-5(`/agents`·`/templates` 를 adapter 로 전환)가 화면을 깨지 않고 가능해진다.

## SYSTEM 과 LEGACY 를 나눈 기준 (이 파일의 핵심 판단)

- **SYSTEM** = **코드에 하드코딩된 기본값**(`agent_registry.DEFAULT_REGISTRY`).
  런타임에 바뀌지 않고 사람이 고칠 수도 없으므로 «제품이 보증하는 자산»이다. 실무에서는
  `agents_registry.json` 이 아직 없는 **새 설치**에서만 나온다 — 즉 SYSTEM 이 0 개라는 것은
  «이미 누군가 손댔다» 는 사실의 보고이며, 분류가 죽어 있다는 뜻이 아니다.
- **LEGACY** = **파일로 존재하는 모든 것.** `agents_registry.json` · `templates/*.json` ·
  `skills/*.md` 가 여기 속한다.

⚠️ `templates/*.json` 을 SYSTEM 으로 분류하지 않은 이유가 중요하다. 코드에서 확인한 사실 둘:

  1. `agent_registry.save_template()` 은 **기존 파일을 그대로 덮어쓴다**(존재 검사는
     `copy_template` 에만 있다). 따라서 제품이 배포한 템플릿과 사용자가 편집한 내용이
     **같은 파일에 섞인다.** 파일만 보고 «제품 원본» 이라고 단정할 수 없다.
  2. `list_templates()` 가 주는 `builtin` 플래그는 «제품 배포물인가» 가 **아니라**
     «`default` 템플릿인가» 를 뜻한다(파일 템플릿은 전부 `False`). 이름에 속아 이 값을
     출처 판단에 쓰면 안 된다.

  출처를 정확히 알 수 없을 때 «모르는 것을 SYSTEM(수정 불가)으로» 두면 사용자가 자기가 만든
  템플릿을 못 고쳐 업무가 막힌다. LEGACY 로 두면 이관 대상으로 표시되고 편집은 종전 경로로
  계속된다 — 틀렸을 때의 대가가 훨씬 작다.

  그리고 LEGACY 의 정의가 실제로 그것이다: **사람이 언제든 고칠 수 있고 승인 이력이 없다.**

## 이 어댑터는 **읽기 전용**이다

파일 쓰기는 종전 경로(`core.agent_registry` · 스킬 개선안 승인)가 계속 담당한다. 어댑터로
고치려는 호출은 `assert_writable_here()` 가 «어디서 바꾸는지» 와 함께 막는다. 그래서 자산마다
`edit_via`(바꾸는 곳)를 실어 준다 — `read_only` 같은 참·거짓 하나로는 «아무도 못 바꾼다» 와
«여기서는 못 바꾼다» 가 구분되지 않는다.

## 파일 자산이 «승인됨」으로 보이는 것에 대하여

파일 자산은 `status=APPROVED`(즉 `runnable=True`)로 노출한다. **지금 실제로 그 정의로 실행되고
있기 때문**이다. DRAFT 로 두면 P3(런타임 강제)가 붙는 순간 전 파이프라인이 실행 불가가 된다.

⚠️ 그러나 `approved_by` 는 **비어 있다** — 파일에는 누가 승인했는지가 없다. 그것을 «관리자가
  승인함» 같은 값으로 채우지 않는다. 대신 `needs_migration=True` 와 `source` 를 실어
  «승인 이력 없이 돌고 있는 자산»임을 호출부가 볼 수 있게 한다.
  MDM 의 «미바인딩 레코드 수를 상시 관측한다» 와 같은 규칙이다 — 관대함을 숨기지 않는다.
"""
from __future__ import annotations

import os
from typing import Any, Dict, FrozenSet, List, Optional

from core import agent_registry as _reg
from core.agent_assets import (
    KIND_AGENT, KIND_SKILL, KIND_WORKFLOW, KINDS, RUNNABLE,
    ST_APPROVED, VIS_ENTERPRISE, VIS_SYSTEM,
    AssetError, AssetNotFound, agent_assets,
)


def _usage_record(asset_key: str, kind: str) -> None:
    """[P4-4] 자산이 **해석된** 순간을 관측에 남긴다.

    ⚠️ 지연 import 다 — `asset_usage` 를 모듈 상단에서 끌어오면 이 어댑터가 계측 모듈에
      의존하게 되고, 계측 쪽 import 오류가 **실행 경로 전체를 막는다.** 계측은 그런 힘을
      가지면 안 된다.
    ⚠️ 예외를 삼킨다. 「사용을 기록하지 못했다」의 대가는 그 자산이 «사용 기록 없음» 으로
      보이는 것뿐이고, 소비자는 관측 기간이 짧으면 애초에 목록을 만들지 않는다."""
    try:
        from core.asset_usage import record as _rec
        _rec(asset_key, kind)
    except Exception:
        pass


#: 파일 자산 id 의 접두사. **접두사로 출처가 보인다** — id 만 보고 «이건 파일 자산이다» 를 안다.
#  DB 자산은 `as_…`(`agent_assets.create`)이므로 절대 겹치지 않는다.
FILE_PREFIX = "file:"

SOURCE_SYSTEM = "SYSTEM"
SOURCE_LEGACY = "LEGACY"

#: 스킬 문서 디렉터리. `agent_registry` 가 경로 상수를 공개하지 않으므로 같은 규칙으로 만든다.
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")


def is_file_asset(asset_id: str) -> bool:
    return str(asset_id or "").startswith(FILE_PREFIX)


def file_asset_id(kind: str, native_id: str) -> str:
    return f"{FILE_PREFIX}{kind}:{native_id}"


def _split(asset_id: str) -> tuple[str, str]:
    """`file:agent:RFP_Analyst` → `("agent", "RFP_Analyst")`."""
    rest = str(asset_id or "")[len(FILE_PREFIX):]
    kind, _, native = rest.partition(":")
    if kind not in KINDS or not native:
        raise AssetNotFound(asset_id)
    return kind, native


#: 종류별 «어디서 바꾸는가». 사용자에게 다음 행동을 알려 주는 값이므로 화면 이름으로 적는다.
_EDIT_VIA = {
    KIND_AGENT: "에이전트 통제소",
    KIND_WORKFLOW: "워크플로우 템플릿 편집",
    KIND_SKILL: "스킬 개선안 승인",
}


def _envelope(kind: str, native_id: str, name_ko: str, body: Dict[str, Any],
              source: str, purpose: str = "") -> Dict[str, Any]:
    """저장소 `get()` 과 **같은 모양**으로 만든다.

    ⚠️ 키를 임의로 줄이지 않는다. 호출부가 «DB 자산인지 파일 자산인지» 를 신경 쓰지 않아야
      P1-5 전환이 가능하고, 키가 빠지면 그 순간 화면이 `undefined` 를 그린다."""
    is_system = source == SOURCE_SYSTEM
    return {
        "asset_id": file_asset_id(kind, native_id),
        "kind": kind,
        "tenant_id": "tenant_default",
        # ★ 파일 자산에는 소유 조직이 없다. 빈 값을 그대로 둔다 — «전사» 로 채우면
        #   나중에 «이 자산은 누구 책임인가» 에 거짓으로 답하게 된다.
        "owner_scope_id": "",
        "entity_mode": "REAL",
        # SYSTEM 은 제품 기본, LEGACY 는 지금 전사가 실제로 쓰는 것이므로 전사 공개가 사실이다.
        "visibility": VIS_SYSTEM if is_system else VIS_ENTERPRISE,
        # 지금 이 정의로 실행되고 있으므로 실행 가능으로 노출한다(위 모듈 주석 참조).
        "status": ST_APPROVED,
        "name_ko": name_ko or native_id,
        "purpose": purpose,
        "current_version": 0,          # 파일에는 버전이 없다 — 0 은 «버전 개념이 없음» 이다
        "created_by": "",
        "approved_by": "",             # ⚠️ 비워 둔다. 없는 승인자를 지어내지 않는다
        "effective_from": "",
        "effective_to": "",
        "created_at": "",
        "updated_at": "",
        "body": body,
        "version_no": 0,
        "versions": [],                # 파일 자산에는 개정 이력이 없다
        "runnable": True,
        # ── 파일 자산만 갖는 표시 ─────────────────────────────────────────
        "source": source,
        "native_id": native_id,
        #: 이 어댑터로는 아무것도 못 쓴다. SYSTEM 은 아예 못 바꾸고, LEGACY 는 종전 화면에서
        #  바꾼다 — 그 «어디서» 를 값으로 준다(빈 값 = 사람이 바꿀 수 없음).
        "edit_via": "" if is_system else _EDIT_VIA.get(kind, ""),
        #: ★ 승인 이력 없이 돌고 있다는 사실. 이걸 숨기면 아무도 이관하지 않는다.
        "needs_migration": True,
        "migration_note": (
            "제품 기본 자산입니다 — 복사해서 조직 자산으로 쓰십시오."
            if is_system else
            "파일로 관리되는 자산입니다 — 승인 이력이 없습니다. 조직 자산으로 이관하십시오."),
    }


def _registry_source() -> str:
    """레지스트리가 파일에서 왔는가(LEGACY), 코드 기본값인가(SYSTEM).

    `agent_registry.load_registry()` 는 파일이 없으면 `DEFAULT_REGISTRY` 를 준다. 즉
    **파일 존재 여부**가 그대로 이 구분이다."""
    return SOURCE_LEGACY if os.path.exists(_reg.REGISTRY_PATH) else SOURCE_SYSTEM


# ── 종류별 파일 자산 ───────────────────────────────────────────────────────
def _agents() -> List[Dict[str, Any]]:
    src = _registry_source()
    try:
        reg = _reg.load_registry()
    except Exception:
        return []
    out = []
    for a in reg.get("agents") or []:
        aid = str(a.get("id") or "").strip()
        if not aid:
            continue
        out.append(_envelope(KIND_AGENT, aid, a.get("name_ko") or aid, dict(a), src,
                             purpose=str(a.get("role") or "")[:200]))
    return out


def _workflows() -> List[Dict[str, Any]]:
    out = []
    # `default` 는 레지스트리 자체다 — 출처도 레지스트리와 같다.
    try:
        base = _reg.load_registry()
        out.append(_envelope(
            KIND_WORKFLOW, _reg.DEFAULT_TEMPLATE_ID,
            base.get("pipeline_name") or "기본 워크플로우", base, _registry_source(),
            purpose=str(base.get("description") or "")[:200]))
    except Exception:
        pass
    # `templates/*.json` — 제품 기본과 사용자 사본이 섞여 있어 전부 LEGACY 로 본다(모듈 주석).
    try:
        for item in _reg.list_templates():
            tid = str(item.get("id") or "")
            if not tid or tid == _reg.DEFAULT_TEMPLATE_ID:
                continue
            try:
                body = _reg.load_template(tid)
            except Exception:
                continue
            out.append(_envelope(KIND_WORKFLOW, tid, item.get("name") or tid, body,
                                 SOURCE_LEGACY,
                                 purpose=str(item.get("description") or "")[:200]))
    except Exception:
        pass
    return out


def _skill_owner_names() -> Dict[str, str]:
    """`스킬 파일명 → 그 스킬을 쓰는 에이전트의 한국어 이름`.

    ★ 스킬의 이름 원천으로 **레지스트리의 `name_ko` 를 먼저 쓴다.** 파일명(`architect_skill`)은
      내부 슬러그이고, 화면에 슬러그를 노출하지 않는 것이 이관 완료 조건이다.

    ⚠️ `default` 레지스트리만 훑으면 안 된다. `sim_*` 스킬 8개는 `mfg_sim` 템플릿 소속이라
      기본 레지스트리에 없고, 그 경우 화면에 `sim_purchase` 같은 슬러그가 그대로 나온다.
      **모든 템플릿을 훑는다** — 이름의 원천은 «그 스킬을 실제로 쓰는 에이전트» 이지
      «기본 파이프라인» 이 아니다."""
    out: Dict[str, str] = {}

    def absorb(reg: Dict[str, Any]) -> None:
        for a in reg.get("agents") or []:
            sk = str(a.get("skill") or "").strip()
            name = str(a.get("name_ko") or "").strip()
            # 먼저 찾은 이름을 유지한다(기본 레지스트리가 우선). 템플릿마다 같은 스킬을 다른
            # 이름의 에이전트가 쓸 수 있고, 그때 이름이 조회마다 바뀌면 안 된다.
            if sk and name and sk not in out:
                out[sk] = name

    try:
        absorb(_reg.load_registry())
    except Exception:
        pass
    try:
        for item in _reg.list_templates():
            tid = str(item.get("id") or "")
            if not tid or tid == _reg.DEFAULT_TEMPLATE_ID:
                continue
            try:
                absorb(_reg.load_template(tid))
            except Exception:
                continue
    except Exception:
        pass
    return out


def _skill_front_matter_name(path: str) -> str:
    """머리말의 `Agent:` 값. **앞부분만 읽는다** — 본문 전체를 목록에 실으면 응답이 커진다.
    이름 한 줄을 위해 1KB 를 읽는 것은 그 대가가 아니다."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(1024)
    except Exception:
        return ""
    for line in head.splitlines()[:12]:
        if line.strip().lower().startswith("agent:"):
            return line.split(":", 1)[1].strip()
    return ""


def _skill_display_name(native: str, owners: Optional[Dict[str, str]] = None) -> str:
    """이름 원천 순서: 레지스트리 한국어 이름 → 머리말 `Agent:` → 파일명.

    ⚠️ 마지막 폴백은 슬러그다. 그러면 «이름을 못 찾았다» 는 사실이 화면에 그대로 보인다 —
      그것을 «에이전트 규칙» 같은 그럴듯한 말로 덮으면 어느 스킬인지 구분조차 안 된다.
    ⚠️ 목록과 상세가 **같은 함수**를 써야 한다. 두 곳에서 따로 계산하면 한쪽만 고쳐졌을 때
      같은 자산이 두 이름으로 보인다."""
    if owners is None:
        owners = _skill_owner_names()
    name = owners.get(native) or _skill_front_matter_name(
        os.path.join(_SKILLS_DIR, f"{native}.md"))
    return f"{name} 규칙" if name else native


def _skills() -> List[Dict[str, Any]]:
    """`skills/*.md` 를 노출한다. **본문은 여기서 읽지 않는다** — 31개 문서 전문을 목록에 실으면
    목록 응답이 수십 KB 가 된다. 본문은 `get()` 에서만 읽는다."""
    if not os.path.isdir(_SKILLS_DIR):
        return []
    owners = _skill_owner_names()
    out = []
    for fn in sorted(os.listdir(_SKILLS_DIR)):
        if not fn.endswith(".md"):
            continue
        native = fn[:-3]
        out.append(_envelope(KIND_SKILL, native, _skill_display_name(native, owners),
                             {"file": fn}, SOURCE_LEGACY,
                             purpose="에이전트 행동 규칙 문서"))
    return out


def file_assets(kind: str) -> List[Dict[str, Any]]:
    """이 종류의 파일 자산 전체. 조회 실패는 **빈 목록으로 삼키지 않는다** —
    각 소스가 개별적으로 실패를 흡수하되(한 파일이 깨져도 나머지는 보인다), 종류 자체를
    모르면 예외를 던진다."""
    if kind == KIND_AGENT:
        return _agents()
    if kind == KIND_WORKFLOW:
        return _workflows()
    if kind == KIND_SKILL:
        return _skills()
    raise AssetError(f"kind 는 {KINDS} 중 하나여야 합니다: {kind}")


def get_file_asset(asset_id: str) -> Dict[str, Any]:
    """파일 자산 하나. 스킬은 여기서 본문(마크다운)을 읽는다."""
    kind, native = _split(asset_id)
    if kind == KIND_SKILL:
        path = os.path.join(_SKILLS_DIR, f"{native}.md")
        if not os.path.exists(path):
            raise AssetNotFound(asset_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            # ⚠️ 읽기 실패를 «빈 스킬» 로 돌려주지 않는다. 빈 규칙은 «규칙 없음» 으로 실행된다.
            raise AssetError(f"스킬 문서를 읽지 못했습니다: {native} — {e}") from e
        return _envelope(KIND_SKILL, native, _skill_display_name(native),
                         {"file": f"{native}.md", "markdown": text},
                         SOURCE_LEGACY, purpose="에이전트 행동 규칙 문서")
    for a in file_assets(kind):
        if a["asset_id"] == asset_id:
            return a
    raise AssetNotFound(asset_id)


# ── [P1-5] 런타임 입구 ────────────────────────────────────────────────────
#: DB 자산 id 접두사. `agent_assets.create` 가 `as_<hex12>` 로 만든다.
DB_PREFIX = "as_"

#: 전역 기본 파이프라인(= 종전 `load_registry()`)의 파일 자산 id. 기존 `GET /agents` 가 쓴다.
DEFAULT_WORKFLOW_ASSET_ID = f"{FILE_PREFIX}{KIND_WORKFLOW}:{_reg.DEFAULT_TEMPLATE_ID}"


def is_db_asset_id(template_id: str) -> bool:
    return str(template_id or "").startswith(DB_PREFIX)


def resolve_workflow(template_id: str, require_runnable: bool = True) -> Dict[str, Any]:
    """[P1-5] **워크플로우 정의를 얻는 단일 입구**(설계 §5.3 «런타임: DB 자산을 기존 그래프
    입력 구조로 변환하는 adapter»).

    `as_…` 면 DB 자산을, 그 밖이면 종전 파일 템플릿을 돌려준다. 두 경우 모두 `agent_registry`
    가 쓰는 것과 **같은 registry dict** 이므로 호출부(`_build_workflow` 등)는 고칠 필요가 없다.

    ★ 입구를 하나로 두는 이유: 실행 경로가 둘이 되면 한쪽만 «승인된 것만 실행» 규칙을 지키게
      되고, 그 경로로 초안이 돈다.

    ⚠️ **승인되지 않은 자산은 실행하지 않는다**(`require_runnable`). P1-1 이 «DRAFT 가 도는
      순간 검토 단계는 형식이 된다» 를 계약으로 잡았고, 그 계약이 실제로 지켜지는 곳은 여기다.
      조회 목적이면 `require_runnable=False` 로 부른다(게시 이력 조회 등).

    ⚠️ **폴백하지 않는다.** `load_template` 은 파일이 깨졌을 때 `DEFAULT_REGISTRY` 로 떨어지는데
      (부팅 안전), DB 자산에는 그 관대함을 주지 않는다 — 조직 워크플로우를 실행했는데 조용히
      기본 파이프라인이 도는 것은 «다른 것이 실행됐다» 이고, 산출물을 보고도 알 수 없다."""
    if not is_db_asset_id(template_id):
        _tid = template_id or _reg.DEFAULT_TEMPLATE_ID
        # [P4-4] 파일 템플릿도 「쓰이는 것」이다 — 여기서 안 세면 파일 템플릿이 전부
        #   「사용 기록 없음」으로 보고된다(관측 구멍이 곧 오보가 된다).
        _usage_record(_tid, "file_template")
        return _reg.load_template_strict(_tid)

    a = agent_assets.get(template_id)                    # 없으면 AssetNotFound
    if a.get("kind") != KIND_WORKFLOW:
        raise AssetError(
            f"'{template_id}' 는 워크플로우 자산이 아닙니다({a.get('kind')}) — "
            f"프로젝트를 실행할 수 없습니다.")
    if require_runnable and not a.get("runnable"):
        raise AssetError(
            f"'{a.get('name_ko') or template_id}' 는 {a.get('status')} 상태입니다 — "
            f"승인된 워크플로우만 실행할 수 있습니다.")
    body = a.get("body") or {}
    if not (body.get("agents") or []):
        raise AssetError(
            f"'{a.get('name_ko') or template_id}' 에 에이전트 정의가 없습니다 — "
            f"기본 파이프라인으로 대체하지 않습니다(무엇이 실행됐는지 알 수 없게 됩니다).")
    # 파일 로더와 같은 정규화·id 스탬프를 거친다. 그러지 않으면 스키마가 보정되지 않은 dict 가
    # 그래프 빌더에 들어가고, 빠진 필드는 실행 중에야 드러난다.
    reg = _reg._normalize(dict(body))
    reg["id"] = template_id                              # 로더가 하는 일과 같다(SSOT 스탬프)
    # [P4-4] ★ **여기까지 온 것만 «쓰였다» 로 센다.** 위 가드(미승인·정의 없음)에서 막힌 것은
    #   실행되지 않았으므로 사용이 아니다 — 거기서 세면 「승인 안 된 자산이 잘 쓰이고 있다」는
    #   모순된 화면이 나온다.
    _usage_record(template_id, f"asset_{KIND_WORKFLOW}")
    return reg


def asset_visible(asset: Dict[str, Any], viewer_scopes: Optional[FrozenSet[str]],
                  viewer_user_id: str) -> bool:
    """이 자산이 이 요청자에게 보이는가. **가시성 판정의 단일 함수.**

    ⚠️ 라우트가 각자 판정을 쓰면 목록에 없는 것이 상세로 열리거나(유출) 목록에 있는 것이
      404 가 된다(고장). 새 API(`agent_governance`)와 기존 API(`factory_control`)가 **같은
      함수**를 봐야 한다."""
    return agent_assets._visible(asset, viewer_scopes, viewer_user_id)


def workflow_summaries(viewer_scopes: Optional[FrozenSet[str]], viewer_user_id: str,
                       include_unapproved: bool = False) -> List[Dict[str, Any]]:
    """[P1-5] 기존 `GET /templates` 가 쓰는 목록. **응답 형태를 바꾸지 않는다** —
    `list_templates()` 와 같은 키(`id`·`name`·`description`·`agent_count`·`builtin`)를 주고,
    새 정보(`source`·`status`·`owner_scope_id`)는 **추가**한다. 기존 화면은 모르는 키를
    무시하고, 새 화면은 그것을 쓴다.

    ★ **승인된 조직 워크플로우만** 넣는다(기본값). 기존 화면은 `status` 를 모르므로 «목록에
      있으면 쓸 수 있다» 고 판단한다 — 초안을 섞으면 그 화면이 초안으로 프로젝트를 만들려 한다.
    """
    out: List[Dict[str, Any]] = []
    for item in _reg.list_templates():
        d = dict(item)
        d["source"] = (SOURCE_LEGACY if item.get("id") != _reg.DEFAULT_TEMPLATE_ID
                       else _registry_source())
        d["status"] = ST_APPROVED          # 파일 템플릿은 지금 실제로 실행되고 있다(P1-2 참조)
        d["owner_scope_id"] = ""
        d["needs_migration"] = True
        out.append(d)

    rows = agent_assets.list_assets(KIND_WORKFLOW, viewer_scopes, viewer_user_id)
    for r in rows:
        # ⚠️ `list_assets` 가 돌려주는 행에는 `runnable` 키가 **없다**(`get()` 만 붙인다).
        #   `r.get("runnable")` 로 판정하면 항상 `None` 이 되어 **모든 조직 워크플로우가
        #   목록에서 사라진다** — 실제로 그렇게 만들었다가 테스트에서 잡혔다. 실행 가능 여부는
        #   저장소의 정의(`RUNNABLE`)로 직접 본다.
        if not include_unapproved and r.get("status") not in RUNNABLE:
            continue
        # ⚠️ 행에는 `body` 도 없다(같은 이유). `r.get("body")` 로 세면 `agent_count` 가 **항상 0**
        #   이 되고, 기존 화면은 그것을 «에이전트 0개 워크플로우» 로 보여 준다 — 0 은 거짓이다.
        #   그래서 정의를 실제로 읽는다. 종전 `list_templates()` 도 템플릿마다 파일을 읽어
        #   세므로 비용은 같다.
        try:
            body = (agent_assets.get(r["asset_id"]).get("body") or {})
        except Exception:
            # 방금 사라진 행은 목록에서 뺀다 — 개수를 0 으로 채워 넣지 않는다.
            continue
        out.append({
            "id": r["asset_id"],
            "name": r.get("name_ko") or r["asset_id"],
            "description": r.get("purpose") or "",
            "agent_count": len(body.get("agents") or []),
            # ★ `builtin` 은 «default 인가» 를 뜻한다(P1-2 주석 참조) — 조직 자산은 아니다.
            "builtin": False,
            "source": "ORG",
            "status": r.get("status"),
            "owner_scope_id": r.get("owner_scope_id") or "",
            "needs_migration": False,      # 승인 이력이 있는 자산이다
        })
    return out


# ── 통합 조회 ─────────────────────────────────────────────────────────────
def list_all(kind: str, viewer_scopes: Optional[FrozenSet[str]], viewer_user_id: str,
             tenant_id: str = "", include_files: bool = True,
             include_retired: bool = False, entity_mode: str = "") -> List[Dict[str, Any]]:
    """DB 자산 + 파일 자산을 합쳐 돌려준다.

    ★ 같은 것이 양쪽에 있어도 **둘 다 보여준다.** 예를 들어 `RFP_Analyst` 를 조직 자산으로
      복사해 두면 원본(파일)과 사본(DB)이 함께 보인다. 원본을 숨기면 «복사해서 쓰십시오» 라는
      규칙이 성립하지 않는다 — 복사할 원본이 목록에 없기 때문이다.

    ⚠️ `viewer_scopes` 는 저장소와 같은 계약이다(필수 인자, `None` 은 «필터하지 않음»).
      여기서 기본값을 만들면 저장소가 지키는 fail-closed 가 이 경로에서만 풀린다.
    """
    rows = agent_assets.list_assets(
        kind, viewer_scopes, viewer_user_id, tenant_id=tenant_id,
        include_retired=include_retired, entity_mode=entity_mode)
    if not include_files:
        return rows
    files = [f for f in file_assets(kind)
             if asset_visible(f, viewer_scopes, viewer_user_id)]
    # 파일 자산을 뒤에 둔다 — 조직이 만든 자산이 먼저 보이는 편이 «내 것부터» 라는 기대에 맞다.
    return rows + files


def get_any(asset_id: str, version_no: int = 0) -> Dict[str, Any]:
    """파일 자산과 DB 자산을 같은 함수로 읽는다."""
    if is_file_asset(asset_id):
        return get_file_asset(asset_id)
    return agent_assets.get(asset_id, version_no=version_no)


def assert_writable_here(asset_id: str) -> None:
    """이 자산을 **범위형 저장소 API 로** 고칠 수 있는가.

    ⚠️ 파일 자산에 `revise`/`approve`/`retire` 를 부르면 저장소는 `AssetNotFound` 를 던진다.
      그 메시지는 «없다» 로 읽히는데 사실은 «여기서 다룰 대상이 아니다» 다. 원인을 잘못 짚으면
      호출부는 자산을 다시 만들려 하고, 그때 같은 정의가 두 벌이 된다."""
    if not is_file_asset(asset_id):
        return
    kind, native = _split(asset_id)
    if kind == KIND_SKILL:
        raise AssetError(
            f"«{native}» 는 파일로 관리되는 스킬 문서입니다 — 스킬 개선안 승인 경로로만 "
            f"바뀝니다. 조직 자산으로 만들려면 복사하십시오.")
    if kind == KIND_WORKFLOW:
        raise AssetError(
            f"«{native}» 는 파일로 관리되는 워크플로우 템플릿입니다 — 템플릿 저장 경로로만 "
            f"바뀝니다. 조직 자산으로 만들려면 복사하십시오.")
    raise AssetError(
        f"«{native}» 는 파일로 관리되는 에이전트 구성입니다 — 에이전트 통제소에서만 바뀝니다. "
        f"조직 자산으로 만들려면 복사하십시오.")


def migration_report(kind: str = "") -> Dict[str, Any]:
    """**승인 이력 없이 돌고 있는 자산이 몇 개인가.** 이 수치를 계속 보이게 두는 것이 이관을
    끝내게 만든다 — 숨기면 아무도 옮기지 않는다(MDM 미바인딩 레코드에서 배운 것).

    ⚠️ 조회 실패를 0 으로 돌려주지 않는다. 실패하면 그 종류를 `unavailable` 에 담는다 —
      «0 개 남았다» 와 «못 셌다» 는 정반대의 사실이다."""
    kinds = [kind] if kind else list(KINDS)
    by_kind: Dict[str, Dict[str, int]] = {}
    unavailable: List[Dict[str, str]] = []
    for k in kinds:
        try:
            fa = file_assets(k)
        except Exception as e:
            unavailable.append({"kind": k, "error": str(e)})
            continue
        by_kind[k] = {
            "system": sum(1 for a in fa if a["source"] == SOURCE_SYSTEM),
            "legacy": sum(1 for a in fa if a["source"] == SOURCE_LEGACY),
            "total": len(fa),
            #: ★ 사용자 이름을 못 찾아 **내부 슬러그가 화면에 그대로 나가는** 자산 수.
            #  어댑터가 이름을 지어낼 수는 없으므로(원천 데이터에 없다) 대신 세어서 남긴다 —
            #  숨기면 아무도 원천을 고치지 않는다.
            "slug_named": sum(1 for a in fa if a["name_ko"] == a["native_id"]),
        }
    return {
        "by_kind": by_kind,
        "pending_total": sum(v["total"] for v in by_kind.values()),
        "unavailable": unavailable,
        "complete": not unavailable,
        "note": ("파일 자산은 승인 이력이 없습니다 — 조직 자산으로 이관하면 누가 언제 승인했는지"
                 " 답할 수 있게 됩니다."),
    }
