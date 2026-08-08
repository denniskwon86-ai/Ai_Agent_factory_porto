"""[D-017 §9 P2-2 / 설계 §8.4] 「이 자산을 **쓰는 프로젝트가 몇 개인가**」.

## 왜 이것이 필요했나

§8.4 는 자산 카드에 `사용 중인 프로젝트 수` 를 요구한다. 그 값이 없으면 **폐기 판단이 눈을
감은 채 이뤄진다** — 실제로 지금 화면의 사용 중단 확인 대화는 「영향 범위를 모르는 채
중단하는 것입니다」라고 사용자에게 자백하고 있다.

## ⚠️⚠️ 이 기능의 가장 위험한 함정 — 착수 시점에 **근거가 0건이었다**

실측(2026-08-08): `projects/` 아래 56개 프로젝트 중 `config_snapshot.json` 을 가진 것이
**0개**다. 기록 지점(`factory_control` 가동 경로)은 있지만 아직 아무 프로젝트도 그곳을
지나지 않았다.

즉 순진하게 집계하면 **모든 자산이 「0개 프로젝트에서 사용」** 으로 나온다. 그 화면을 본
사람은 전부 폐기해도 된다고 읽는다. 그리고 지운 뒤에야 그것이 「안 쓰인 것」이 아니라
**「아직 기록이 없는 것」** 이었음을 안다. P4-1(관측률 8%)·P4-4(미사용 판단 불가)·
`asset_usage`(관측 시작일) 가 전부 같은 함정을 지났다.

★ 그래서 이 모듈은 숫자를 **혼자 내보내지 않는다.** 항상 다음을 함께 낸다:

    projects_total     — 프로젝트가 몇 개인가
    projects_observed  — 그중 **구성을 기록한** 프로젝트가 몇 개인가  ← 분모
    available/error    — 스캔 자체가 됐는가

`projects_observed == 0` 이면 소비자는 **숫자를 쓰지 않는다.** 「0개 프로젝트가 사용」이
아니라 「아직 아무 프로젝트도 구성을 기록하지 않았습니다」가 참이다. 둘은 다른 문장이고,
사용자가 내리는 결정도 다르다.

## ⚠️ 키가 어긋나면 교집합이 **통째로 0** 이 된다

`asset_usage.skill_key` 가 정확히 그 실패를 겪었다(2026-08-07): 레지스트리는 `rfp_skill`,
소비자는 `rfp_skill.md` 를 써서 교집합이 0건이었고, **매 실행마다 쓰이는 스킬 31개가 전부
«사용 기록 없음»** 으로 보고될 참이었다. 관측을 켜 놓고도 「전부 정리 대상」이 나온다.

그래서 매칭 키를 `usage_keys()` **한 함수**에 모으고, 그 함수가 실제 파일 자산 id 규약
(`agent_asset_adapter.file_asset_id` = `file:<kind>:<native>`)을 따르는지 테스트로 고정한다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Set

from core.config_snapshot import SNAPSHOT_FILE

#: 자산 종류별로 스냅샷의 **어느 축**과 맞추는가.
#:   워크플로우 → 어느 템플릿으로 돌았는가
#:   에이전트   → 어떤 에이전트가 참여했는가
#:   스킬       → 어떤 행동 규칙을 읽었는가
_AXIS_BY_KIND = {"workflow": "template_id", "agent": "agents", "skill": "skills"}


def usage_keys(asset: Dict[str, Any]) -> Set[str]:
    """이 자산이 스냅샷에 **어떤 이름으로** 남는가.

    ⚠️ 여기가 유일한 매칭 규약이다. 호출부마다 다시 만들면 한쪽만 고쳐졌을 때 교집합이 0 이
      되고, 그 증상은 「이 자산은 아무도 안 쓴다」라는 **그럴듯한 거짓말**이다.

    세 가지를 모두 키로 인정한다 — 스냅샷이 무엇을 적었는지가 경로마다 다르기 때문이다:
    · `asset_id` 그대로            (DB 자산을 template_id 로 쓴 경우)
    · 파일 자산의 `native` 부분     (`file:agent:RFP_Analyst` → `RFP_Analyst`)
    · 본문의 `id`                  (DB 자산이 레지스트리로 펼쳐질 때 쓰는 이름)
    """
    keys: Set[str] = set()
    aid = str(asset.get("asset_id") or "").strip()
    if aid:
        keys.add(aid)
        if aid.startswith("file:"):
            _, _, rest = aid.partition(":")
            _, _, native = rest.partition(":")
            if native:
                keys.add(native)
    body = asset.get("body") or {}
    if isinstance(body, dict):
        for k in ("id", "template_id"):
            v = str(body.get(k) or "").strip()
            if v:
                keys.add(v)
    return keys


def _snapshot_refs(entry: Dict[str, Any]) -> Dict[str, Set[str]]:
    """스냅샷 한 줄이 참조하는 이름들을 축별로."""
    tid = str(entry.get("template_id") or "").strip()
    return {
        "template_id": {tid} if tid else set(),
        "agents": {str(x) for x in (entry.get("agents") or []) if x},
        #: ⚠️ 옛 스냅샷에는 `skills` 키가 **없다**(2026-08-08 이전). 없음을 «스킬 0개» 로
        #:   읽으면 스킬이 전부 미사용으로 보고된다 — `records_skills` 로 그 구분을 낸다.
        "skills": {str(x) for x in (entry.get("skills") or []) if x},
    }


def scan_projects(projects_dir: Optional[str] = None) -> Dict[str, Any]:
    """프로젝트 작업공간을 훑어 «어느 프로젝트가 무엇을 참조하는가» 를 모은다.

    ★ `workspace_path()` 를 부른다 — `PROJECTS_DIR` 을 모듈 상단에서 값으로 복사하면 그
      순간 값이 고정돼 테스트가 격리 지점을 덮을 수 없다(`core/paths.py` 머리말).
    ⚠️ 스냅샷의 `current` 만 본다. `history` 까지 세면 **한때 썼던** 프로젝트가 「쓰는 중」
      으로 잡히고, 그러면 폐기 판단이 영원히 막힌다. 「지금 무엇으로 도는가」가 질문이다.
    """
    if projects_dir is None:
        from core.paths import workspace_path
        projects_dir = workspace_path()

    out: Dict[str, Any] = {"available": True, "error": "", "projects_total": 0,
                           "projects_observed": 0, "records_skills": 0, "by_project": {}}
    try:
        names = sorted(n for n in os.listdir(projects_dir)
                       if os.path.isdir(os.path.join(projects_dir, n)))
    except FileNotFoundError:
        # ★ 「프로젝트 폴더가 없다」와 「스캔에 실패했다」는 다르다. 전자는 정상적인 0 이다.
        return out
    except Exception as e:                                            # pragma: no cover
        # ⚠️ 실패를 «프로젝트 0개» 로 돌려주지 않는다 — 그러면 모든 자산이 미사용으로 보인다.
        out.update(available=False, error=f"{type(e).__name__}: {e}")
        return out

    out["projects_total"] = len(names)
    for name in names:
        path = os.path.join(projects_dir, name, SNAPSHOT_FILE)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            #: 한 프로젝트의 스냅샷이 깨져도 나머지는 센다. 다만 **관측된 것으로 세지 않는다**
            #: — 읽지 못한 것을 「참조 없음」으로 두면 분모만 늘어 사용률이 낮아 보인다.
            continue
        cur = data.get("current") or {}
        if not isinstance(cur, dict) or not cur:
            continue
        out["projects_observed"] += 1
        if "skills" in cur:
            out["records_skills"] += 1
        out["by_project"][name] = _snapshot_refs(cur)
    return out


def usage_for(assets: Iterable[Dict[str, Any]], kind: str,
              projects_dir: Optional[str] = None,
              scan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """자산 목록에 대해 「쓰는 프로젝트」를 센다.

    ⚠️ 반환의 `project_count` 를 **혼자 읽지 말 것.** `projects_observed` 가 0 이면 그 값은
      「쓰이지 않는다」가 아니라 「아직 모른다」이다. 두 상태를 화면이 구분하도록
      `countable` 을 자산마다 함께 낸다.
    """
    axis = _AXIS_BY_KIND.get(kind)
    s = scan if scan is not None else scan_projects(projects_dir)
    observed = int(s.get("projects_observed") or 0)

    #: ★ 스킬 축은 **2026-08-08 이후 스냅샷에만** 있다. 그 이전 기록만 있는 상태에서 0 을
    #:   내면 「전부 미사용」이 되므로, 스킬을 셀 수 있는 스냅샷 수를 따로 본다.
    axis_observed = int(s.get("records_skills") or 0) if axis == "skills" else observed

    usage: Dict[str, Any] = {}
    for a in assets:
        keys = usage_keys(a)
        hits: List[str] = []
        if axis and keys:
            for pname, refs in (s.get("by_project") or {}).items():
                if keys & refs.get(axis, set()):
                    hits.append(pname)
        usage[str(a.get("asset_id") or "")] = {
            "project_count": len(hits),
            #: 어느 프로젝트인지도 준다 — 「3개」만으로는 확인하러 갈 곳이 없다.
            "projects": sorted(hits)[:20],
            #: ★ 이 자산의 수를 **믿어도 되는가.** 관측이 0 이면 False 다.
            "countable": bool(s.get("available")) and axis_observed > 0,
        }
    return {
        "available": bool(s.get("available")),
        "error": str(s.get("error") or ""),
        "projects_total": int(s.get("projects_total") or 0),
        "projects_observed": observed,
        #: 이 축을 실제로 셀 수 있는 스냅샷 수. 스킬은 이 값이 `projects_observed` 보다 작다.
        "axis_observed": axis_observed,
        "axis": axis or "",
        "usage": usage,
    }
