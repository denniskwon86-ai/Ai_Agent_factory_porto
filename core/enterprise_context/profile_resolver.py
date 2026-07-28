"""프로필 상속 해석과 템플릿↔마스터 바인딩 — ECM 로드맵 **E2**.

## ① 프로필 상속 병합 (§4.4)

```text
산업 공통 프로필(= playbooks/*.json 저작 기본값, DECISIONS.md D-002)
  → 기업집단 → 법인 → 사업부 → 사업장/공장
    → 프로젝트/시나리오 오버레이
```

**충돌 시 가장 하위의 '승인된' 프로필이 이긴다.** 두 단어가 다 중요하다:
  · *가장 하위* — 현장이 본사보다 자기 공정을 잘 안다. 상위가 하위를 덮으면 현장 예외가 삭제된다
    (§13 위험표 "업종 템플릿이 강제되어 현장 예외를 삭제").
  · *승인된* — 미승인(DRAFT) 프로필은 병합에 참여하지 않는다. 검토 전 값이 프롬프트에 들어가면
    안 된다.

`inheritance_mode='replace'` 인 프로필은 **상위를 버린다.** 병합으로는 표현할 수 없는 경우가 있다 —
예를 들어 상위가 정한 공정 목록을 하위가 완전히 다른 공정으로 대체할 때, merge 로는 상위 항목이
남아 실제로 없는 공정이 프롬프트에 들어간다.

## ② 템플릿↔마스터 바인딩 (감사 ENTERPRISE-01 Action 3)

Antigravity 감사가 지적한 위험: "템플릿이 마스터 데이터의 어느 섹션을 컨텍스트로 바인딩해야
하는지 명시하지 않으면 **LLM 이 마스터를 무시하고 환각으로 수치를 지어낸다.**"

⚠️ 감사표는 시나리오 ID 기준이었으나 **템플릿 기준으로 정규화**했다(`DECISIONS.md` R-002):
  프로젝트는 `template_id` 를 갖고 시나리오 ID 는 테스트 개념이라, 시나리오로 묶으면 실제
  사용자 프로젝트에 적용할 키가 없다. 감사표의 '템플릿' 열이 1:1 이라 정보 손실은 없다.

⚠️ 마스터 **본문은 여기에 담지 않는다**(`DECISIONS.md` R-001). MDM(`core/master_data.py`)이
  진실원본이고 여기는 "어느 섹션을 써야 하는가"라는 바인딩만 갖는다. 본문을 복사하면 같은 데이터가
  두 저장소에 생겨 진실원본이 모호해진다(ECM §8.2 역할 분리).
"""
import copy
from typing import Any, Dict, List, Optional

from core.enterprise_context.models import (PROFILE_KINDS, REL_OPERATING_PARENT,
                                            EnterpriseProfile)
from core.enterprise_context.repository import EcmRepository, ecm_repository
from core.enterprise_context.resolver import EcmResolver, ecm_resolver

# ── 감사 Action 3 — 템플릿별 필수 마스터 바인딩 ────────────────────────────
# `docs/master_data/*.json` 의 루트 키와 1:1 로 맞춘다(실측 확인: material_master ·
#   bill_of_materials · equipment_master · quality_master · siop_finance_master).
# `deterministic` = 결정론적 엔진이 반드시 개입해야 하는가. True 면 LLM 이 그 수치를 만들면 안 된다.
TEMPLATE_MASTER_BINDINGS: Dict[str, Dict[str, Any]] = {
    "manufacturing-cost-analysis": {
        "required_master_sections": ["material_master", "bill_of_materials",
                                     "siop_finance_master"],
        "deterministic": True,
        "reason": "BOM 원가 롤업은 계산이다. LLM 이 원가를 추정하면 그 숫자로 의사결정이 일어난다.",
    },
    "manufacturing-market-forecast": {
        "required_master_sections": ["siop_finance_master"],
        "deterministic": False,
        "reason": "통계 모델링 영역. 다만 LME 시세·환율은 마스터의 확정값을 써야 한다.",
    },
    "manufacturing-production": {
        "required_master_sections": ["equipment_master", "bill_of_materials"],
        "deterministic": True,
        "reason": "MRP 와 병목 가동률(OEE·MTBF·MTTR)은 계산이다.",
    },
    "manufacturing-qc": {
        "required_master_sections": ["quality_master"],
        "deterministic": True,
        "reason": "SPC 공정능력지수(Cpk)는 공차와 측정값으로 계산한다.",
    },
    "mfg_sim": {
        "required_master_sections": ["material_master", "bill_of_materials", "equipment_master",
                                     "quality_master", "siop_finance_master"],
        "deterministic": True,
        "reason": "What-if 오버레이 계산에 M1~M4 전체가 필요하다(감사: 절대 필수).",
    },
}


def binding_for_template(template_id: str) -> Optional[Dict[str, Any]]:
    """템플릿의 필수 마스터 바인딩. 등록되지 않은 템플릿은 `None`(제약 없음)."""
    b = TEMPLATE_MASTER_BINDINGS.get(template_id or "")
    return dict(b) if b else None


def render_binding_block(template_id: str) -> str:
    """프롬프트에 넣을 바인딩 지시문. **환각 차단이 목적**이라 문구가 단호해야 한다.

    ⚠️ 본문(실제 마스터 값)은 넣지 않는다 — 그건 `master_data.get_master_context()` 가 결정론적으로
      주입한다. 여기는 "이 값들을 반드시 그 주입본에서 가져와 쓰고, 없으면 지어내지 말고 없다고
      말하라"는 규칙만 싣는다. 둘을 합치면 프롬프트 예산이 두 배가 되고 진실원본이 흐려진다."""
    b = binding_for_template(template_id)
    if not b:
        return ""
    lines = ["[기준정보 바인딩 규칙]",
             f"이 작업은 다음 기준정보 영역을 **반드시** 근거로 사용한다: "
             f"{', '.join(b['required_master_sections'])}."]
    if b["deterministic"]:
        lines.append("⚠️ 이 영역의 수치는 **계산 결과**다. 추정하거나 지어내지 말고, 주입된 "
                     "기준정보의 값을 그대로 쓰거나 명시된 산식으로 계산하라.")
        lines.append("⚠️ 필요한 기준정보가 주입되지 않았다면 값을 만들지 말고 "
                     "'해당 기준정보가 없어 계산할 수 없음'이라고 밝히고 필요한 항목을 나열하라.")
    else:
        lines.append("이 영역의 확정값(시세·환율 등)은 주입된 기준정보를 우선한다.")
    lines.append(f"근거: {b['reason']}")
    return "\n".join(lines)


# ── 프로필 상속 병합 ──────────────────────────────────────────────────────
def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """하위(`over`)가 상위(`base`)를 덮는 깊은 병합.

    ⚠️ **리스트는 병합하지 않고 교체한다.** 예: 상위가 공정 5개, 하위가 3개면 하위의 3개가 그
      조직의 공정이다. 이어붙이면 그 공장에 없는 공정이 프롬프트에 들어가 환각의 근거가 된다."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class ProfileResolver:
    def __init__(self, repo: EcmRepository = None, resolver: EcmResolver = None):
        self.repo = repo or ecm_repository
        self.scope = resolver or ecm_resolver

    def inheritance_chain(self, node_id: str) -> List[str]:
        """상위 → 하위 순서의 노드 체인(병합 적용 순서). 마지막이 자기 자신이다."""
        if not node_id:
            return []
        ancestors = self.scope.ancestors(node_id, REL_OPERATING_PARENT)
        # `ancestors` 는 가까운 것부터라서 뒤집어야 '상위 → 하위'가 된다.
        return list(reversed(ancestors)) + [node_id]

    def resolve(self, node_id: str, profile_kind: str,
                industry_base: Optional[Dict[str, Any]] = None,
                overlay: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """상속을 해석한 실행 프로필(§9 `GET /contexts/{scope_id}/resolved-profile`).

        `industry_base`: 산업 공통 층. 플레이북이 이 자리를 담당한다(D-002) — 호출부가 넘긴다.
        `overlay`: 프로젝트/시나리오의 명시적 오버레이(체인 최하위).

        반환에 **`sources`(적용 순서)와 `skipped`(미승인으로 제외된 것)를 함께** 담는다.
        "이 값이 어디서 왔나"를 답할 수 없으면 프로필 기반 추천을 신뢰할 수 없다(§5.2 근거 표시)."""
        if profile_kind not in PROFILE_KINDS:
            from core.enterprise_context.models import EcmError
            raise EcmError(f"profile_kind 는 {PROFILE_KINDS} 중 하나여야 합니다.")

        merged: Dict[str, Any] = copy.deepcopy(industry_base or {})
        sources: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        if industry_base:
            sources.append({"layer": "industry_common", "scope_node_id": "",
                            "profile_id": "", "mode": "merge"})

        for nid in self.inheritance_chain(node_id):
            for p in self.repo.list_profiles(scope_node_id=nid, profile_kind=profile_kind):
                if not p.is_effective:
                    # 미승인은 병합에 참여하지 않는다 — 검토 전 값이 프롬프트에 들어가면 안 된다.
                    skipped.append({"profile_id": p.profile_id, "scope_node_id": nid,
                                    "status": p.status,
                                    "reason": "승인되지 않아 상속에 참여하지 않습니다."})
                    continue
                if p.inheritance_mode == "replace":
                    # 상위를 버린다 — 병합으로 표현할 수 없는 '완전 대체'가 필요한 경우가 있다.
                    merged = copy.deepcopy(p.payload)
                    sources = [{"layer": "node", "scope_node_id": nid,
                                "profile_id": p.profile_id, "mode": "replace"}]
                else:
                    merged = _deep_merge(merged, p.payload)
                    sources.append({"layer": "node", "scope_node_id": nid,
                                    "profile_id": p.profile_id, "mode": "merge"})

        if overlay:
            merged = _deep_merge(merged, overlay)
            sources.append({"layer": "overlay", "scope_node_id": node_id,
                            "profile_id": "", "mode": "merge"})

        return {"profile_kind": profile_kind, "scope_node_id": node_id, "payload": merged,
                "sources": sources, "skipped": skipped,
                "chain": self.inheritance_chain(node_id)}

    def resolve_all(self, node_id: str,
                    industry_bases: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """6개 프로필 묶음을 한 번에 해석한다(§4.4)."""
        bases = industry_bases or {}
        return {kind: self.resolve(node_id, kind, bases.get(kind)) for kind in PROFILE_KINDS}


profile_resolver = ProfileResolver()


# ══════════════════════════════════════════════════════════════════════════
# 플레이북 ↔ 산업 공통 프로필 연결 (DECISIONS.md D-002)
# ══════════════════════════════════════════════════════════════════════════
def playbook_industry_base(pb) -> Dict[str, Any]:
    """플레이북을 `data_profile` 의 **산업 공통 층**으로 변환한다.

    D-002: 플레이북이 §4.4 체인 최상위다. 도메인 지식은 git diff 가 되는 파일에 남기고
    조직별 차이만 DB(`enterprise_profiles`)가 담는다. 이 함수가 그 둘을 잇는다.

    변환은 **요구사항 키 목록과 필요도**만 담는다 — 질문 문구·결손 안내 같은 본문은 플레이북이
    진실원본이므로 복사하지 않는다(복사하면 두 곳이 어긋난다)."""
    return {
        "playbook_id": pb.playbook_id,
        "business_type": pb.business_type,
        "recommended_template_id": pb.recommended_template_id,
        "requirements": {r.key: {"necessity": r.necessity,
                                 "requirement_type": r.requirement_type,
                                 "owner_department": r.owner_department}
                         for r in pb.data_requirements},
    }


def apply_org_profile_to_requirements(pb, resolved_data_profile: Dict[str, Any]) -> Dict[str, Any]:
    """조직 프로필이 상담 요구사항을 어떻게 바꾸는지 계산한다(설계서 수용 기준 3).

    "같은 '생산계획' 요청이라도 선택 조직의 업종·공정·데이터 계약에 따라 다른 템플릿·질문·
    에이전트 추천 근거가 나온다" — 그 차이를 만드는 지점이다.

    조직 `data_profile` 이 쓸 수 있는 키:
      · `requirement_overrides: {키: {"necessity": "required|recommended|optional"}}`
        — 필요도를 조직 사정에 맞게 올리거나 내린다.
      · `excluded_requirements: [키]` — 이 조직에는 해당 없는 요구사항.
      · `additional_requirements: [{key, canonical_term, necessity, ...}]` — 조직 고유 요구사항.

    ⚠️ **필수(`required`)를 조직이 제외하는 것은 허용하지 않는다.** 플레이북이 "이것 없으면 성립
      안 됨"이라고 선언한 것을 조직 설정으로 조용히 지우면, 준비도가 부풀려지고 결손 안내도 뜨지
      않는다(M0-a 에서 같은 유형의 결함을 겪었다). 대신 `blocked` 로 돌려 사람이 보게 한다.

    반환: `{overrides, excluded, additional, blocked}` — 무엇이 왜 적용/거부됐는지 전부 보인다."""
    payload = resolved_data_profile or {}
    by_key = {r.key: r for r in pb.data_requirements}

    overrides: Dict[str, Dict[str, Any]] = {}
    blocked: List[Dict[str, str]] = []
    for key, ov in (payload.get("requirement_overrides") or {}).items():
        if key not in by_key:
            blocked.append({"key": key, "reason": "플레이북에 없는 요구사항 키입니다."})
            continue
        nec = (ov or {}).get("necessity")
        if nec and nec not in ("required", "recommended", "optional"):
            blocked.append({"key": key, "reason": f"알 수 없는 necessity: {nec}"})
            continue
        if by_key[key].necessity == "required" and nec in ("optional",):
            blocked.append({"key": key,
                            "reason": "플레이북이 필수로 선언한 요구사항을 선택으로 내릴 수 없습니다."})
            continue
        overrides[key] = {"necessity": nec} if nec else {}

    excluded: List[str] = []
    for key in (payload.get("excluded_requirements") or []):
        if key not in by_key:
            blocked.append({"key": key, "reason": "플레이북에 없는 요구사항 키입니다."})
            continue
        if by_key[key].necessity == "required":
            blocked.append({"key": key,
                            "reason": "플레이북이 필수로 선언한 요구사항은 제외할 수 없습니다."})
            continue
        excluded.append(key)

    additional: List[Dict[str, Any]] = []
    for item in (payload.get("additional_requirements") or []):
        if not isinstance(item, dict) or not item.get("key"):
            blocked.append({"key": str(item)[:40], "reason": "key 가 없는 추가 요구사항입니다."})
            continue
        if item["key"] in by_key:
            blocked.append({"key": item["key"], "reason": "플레이북 요구사항과 키가 충돌합니다."})
            continue
        additional.append(item)

    return {"overrides": overrides, "excluded": excluded, "additional": additional,
            "blocked": blocked}
