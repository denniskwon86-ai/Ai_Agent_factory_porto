"""[D-017 §9 P2-3] AI 파이프라인 추천에 **이 조직이 실제로 쓸 수 있는 것**을 넣는다.

## 왜 필요한가

`POST /ai-recommend/pipeline` 은 사용자 문장 하나만 LLM 에 넘겼다. 그래서 추천된 파이프라인은
**존재하지 않는 데이터와 접근할 수 없는 도구**를 전제로 설계된다. 그 결과는 두 갈래인데 둘 다
나쁘다:

· 실행 단계에서 도구 권한 교집합(P3-3)에 걸려 죽는다 — 사용자는 「AI 가 추천한 대로 했는데
  안 된다」를 겪고, 무엇을 고쳐야 하는지는 아무도 말해 주지 않는다.
· 또는 통제가 없는 경로로 흘러 **권한 밖 자원을 실제로 건드린다.**

★ 그래서 설계 단계에서 «가능한 것» 을 알려 준다. 통제를 사후 거부가 아니라 **사전 안내**로
  옮기는 일이고, 이것이 P2-3 의 목적이다.

## ⚠️ 이 파일의 핵심 규칙 — 모르면 «없음» 이라고 말하지 않는다

조회에 실패했을 때 「도구 0개」라고 프롬프트에 쓰면 LLM 은 **도구 없이 설계**하거나 **도구를
지어낸다.** 둘 다 조용히 틀린다. 그래서 각 항목은 세 상태를 갖는다:

    []      확인했고 정말 없다
    [...]   확인했고 이것들이 있다
    None    **확인하지 못했다** → 프롬프트에 「확인하지 못했습니다」라고 적는다

이 저장소가 반복해 지키는 «조회 실패 ≠ 0건» 을 프롬프트에도 적용하는 것이다. LLM 은 빈
목록과 «모름» 을 구분하지 못하므로 **문장으로** 구분해 준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

#: 프롬프트에 넣을 최대 항목 수. 길면 모델이 뒤쪽을 무시하고, 비용도 늘어난다.
MAX_ITEMS = 25


@dataclass(frozen=True)
class DesignContext:
    """추천에 넣을 «이 조직의 현재». 각 필드의 `None` 은 **확인하지 못함**이다."""
    scope_node_id: str = ""
    org_label: str = ""
    #: 접근 가능한 커넥터(도구) — `{"id","name","kind","status"}`
    connectors: Optional[List[Dict[str, Any]]] = None
    #: 참조 데이터 자산
    data_assets: Optional[List[Dict[str, Any]]] = None
    #: 연결된 지식팩
    knowledge_packs: Optional[List[str]] = None


def _safe(fn, *a, **kw):
    """조회 실패를 **`None`(모름)** 으로 돌려준다. 빈 목록으로 바꾸지 않는다.

    ⚠️⚠️ **프로그래밍 오류를 «확인하지 못함» 으로 위장하지 않는다.** 처음에 모듈 이름을
      잘못 적었더니(`core.knowledge_hub` — 없는 모듈) 이 함수가 `ImportError` 를 삼켰고,
      프롬프트에는 「지식 허브를 읽지 못했습니다」가 나갔다. **틀린 이유를 그럴듯하게 말하는**
      상태이며, 그런 오류는 아무도 고치지 않는다 — 화면상 «저장소가 잠깐 안 읽혔나 보다» 로
      읽히기 때문이다.

    ★ 그래서 이름·속성 오류는 소리를 낸다(추천은 계속 동작해야 하므로 예외를 올리지는 않되,
      로그에 «버그» 라고 적는다). 그리고 `tests/test_agent_design_context.py` 가 세 수집기의
      import 가 실제로 풀리는지 확인해 이 유형을 **테스트 단계에서** 잡는다."""
    try:
        return fn(*a, **kw)
    except (ImportError, AttributeError, NameError, TypeError) as e:
        print(f"🐞 [agent_design_context] 수집기 버그({fn.__name__}): {type(e).__name__}: {e}")
        return None
    except Exception:
        return None                    # 저장소 잠금·파일 없음 등 — 진짜 «확인하지 못함»


def collect(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
            viewer_clearance: str = "", include_descendants: bool = False,
            org_label: str = "") -> DesignContext:
    """이 문맥에서 **실제로 보이는** 도구·데이터를 모은다.

    ⚠️ 범위 판정을 여기서 다시 구현하지 않는다 — 각 저장소의 `list_*`/`visible_*` 이 이미
      `filter_visible` 단일 지점을 지난다. 여기서 또 거르면 규칙이 갈라지고, 갈라진 권한
      판정은 «유출이거나 실명» 이다(`reference_registry.visible_assets` 주석)."""
    conns = _safe(_connectors, scope_node_id, tenant_id, entity_mode,
                  viewer_clearance, include_descendants)
    assets = _safe(_assets, scope_node_id, viewer_clearance, include_descendants)
    packs = _safe(_packs, scope_node_id)
    return DesignContext(scope_node_id=scope_node_id, org_label=org_label,
                         connectors=conns, data_assets=assets, knowledge_packs=packs)


def _connectors(scope_node_id, tenant_id, entity_mode, clearance, descend):
    from core.connector_registry import connector_registry
    rows = connector_registry.list_connectors(
        scope_node_id=scope_node_id, tenant_id=tenant_id, entity_mode=entity_mode or "REAL",
        viewer_clearance=clearance, include_descendants=descend) or []
    out = []
    for r in rows:
        # ⚠️ 활성이 아닌 커넥터를 «쓸 수 있는 도구» 로 내보내지 않는다. 계약을 통과해도
        #   조회가 실패한다(`connector_control.list_adapters` 의 note 가 적은 그 상태).
        if str(r.get("status") or "").lower() not in ("active", "enabled"):
            continue
        out.append({"id": r.get("connector_id"), "name": r.get("name") or r.get("connector_id"),
                    "kind": r.get("kind") or "", "access": r.get("access_mode") or ""})
    return out[:MAX_ITEMS]


def _assets(scope_node_id, clearance, descend):
    from core.reference_registry import visible_assets
    rows = visible_assets(scope_node_id=scope_node_id, viewer_clearance=clearance,
                          include_descendants=descend) or []
    return [{"id": r.get("asset_id") or r.get("id"),
             "name": r.get("name") or r.get("title") or "",
             "kind": r.get("kind") or r.get("asset_kind") or ""} for r in rows][:MAX_ITEMS]


def _packs(scope_node_id):
    # ⚠️ 모듈 이름을 추측하지 말 것. 처음에 `core.knowledge_hub` 라고 썼는데 그런 모듈은 없고,
    #   `_safe` 가 그 ImportError 를 «확인하지 못함» 으로 삼켜서 프롬프트에 「지식 허브를 읽지
    #   못했습니다」가 나갔다 — **틀린 이유를 그럴듯하게 말하는** 상태였다. 정본은
    #   `core/knowledge_base.py` 의 `knowledge_base` 다.
    from core.knowledge_base import knowledge_base
    packs = knowledge_base.list_packs() or []
    return [str(p.get("pack_id") or p.get("id") or p.get("name") or "")
            for p in packs][:MAX_ITEMS]


def _section(title: str, rows: Optional[List], render, unknown_note: str) -> str:
    """★ **세 상태를 문장으로 구분한다.** LLM 은 빈 목록과 «모름» 을 구분하지 못한다."""
    if rows is None:
        return f"### {title}\n(확인하지 못했습니다 — {unknown_note})\n"
    if not rows:
        return f"### {title}\n(확인했고, 등록된 것이 없습니다.)\n"
    return f"### {title}\n" + "\n".join(f"- {render(r)}" for r in rows) + "\n"


def to_prompt(ctx: DesignContext) -> str:
    """프롬프트에 끼울 블록. **문맥이 통째로 비면 빈 문자열**을 돌려준다.

    ⚠️ 아무것도 모르면서 「사용할 수 있는 도구가 없습니다」라고 쓰지 않는다 — 그 문장은
      모델을 «도구 없는 설계» 로 몰아간다. 모르면 아예 말하지 않는 편이 낫다."""
    known = [x for x in (ctx.connectors, ctx.data_assets, ctx.knowledge_packs) if x is not None]
    if not known and not ctx.scope_node_id:
        return ""

    where = ctx.org_label or ctx.scope_node_id or "(조직 미지정)"
    head = (f"## 이 설계가 놓일 자리\n\n조직 범위: **{where}**\n\n"
            "아래는 이 조직이 **지금 실제로 접근할 수 있는 것**입니다. "
            "여기 없는 데이터·도구를 전제로 설계하면 실행 단계에서 권한 검사에 걸려 실패합니다.\n"
            "★ 확인하지 못한 항목은 «없음» 이 아닙니다. 그런 항목은 "
            "**전제로 삼지 말고, 필요하면 그 사실을 설계 근거에 적으십시오.**\n\n")

    body = (
        _section("사용할 수 있는 도구(커넥터)", ctx.connectors,
                 lambda r: f"{r['id']} — {r['name']} ({r['kind'] or '종류 미기재'})",
                 "커넥터 저장소를 읽지 못했습니다")
        + "\n"
        + _section("참조할 수 있는 데이터 자산", ctx.data_assets,
                   lambda r: f"{r['id']} — {r['name']}" + (f" [{r['kind']}]" if r["kind"] else ""),
                   "참조 데이터 대장을 읽지 못했습니다")
        + "\n"
        + _section("연결된 지식팩", ctx.knowledge_packs, lambda r: str(r),
                   "지식 허브를 읽지 못했습니다")
    )
    return head + body + "\n"
