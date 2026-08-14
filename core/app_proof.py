"""★★★ [G1-B 3.5] **앱 증명의 사실은 서버가 산출한다.**

교차검토 `[G1-B-I3-REVIEW-82]` 의 계약 (2):

> 서버가 release·app·Manifest·현재 tenant/entity/scope·사용자·세션 해시를 직접 해석하고
> **capability 를 서버에서 산출**한다.

## 왜 클라이언트 입력을 받지 않는가

발급 요청이 `capabilities` 를 실어 보낼 수 있으면, 증명은 「이 화면이 이 앱을 열고 있다」는
사실이 아니라 **「부르는 쪽이 원한다고 말한 권한」** 이 된다. 그러면 부모 코드의 실수 하나,
또는 그 코드를 부르는 어떤 경로 하나가 곧 권한 상승이다.

그래서 발급 API 가 받는 것은 **`release_id` 하나**이고, 나머지는 전부 여기서 만든다.

## 권한은 «넘겨받는» 것이지 «생기는» 것이 아니다

증명의 capability 는 **세 가지의 교집합**이다:

    ① 지금 이 사용자가 그 릴리스에 대해 실제로 할 수 있는 것  (정책 결정점이 답한다)
    ② 매니페스트가 «하겠다» 고 선언한 것                      (앱이 말한 것)
    ③ 앱 데이터 평면이 가진 행동                              (read·write·delete·manage)

⚠️ ① 을 빼면 권한을 회수해도 증명 수명 동안 살아 있다. ② 를 빼면 선언하지 않은 앱이
  데이터를 만진다. 둘 다 실제로 이 저장소에서 한 번씩 열려 있던 구멍이다.

LLM 0콜.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from core import app_policy
from core.app_policy import ACTIONS, DELETE, MANAGE, READ, WRITE

#: ★★★ 매니페스트가 쓰는 낱말 → **정책 행동**.
#:
#: 매니페스트의 capability 는 `"material_plan.read"`·`{"resource":…, "actions":["create"]}`
#: 처럼 **업무 낱말**이고, 정책 행동은 넷뿐이다. 그 사이를 잇는 표가 없으면 누군가 코드
#: 안에서 즉석으로 잇게 되고, 그때부터 「어느 선언이 무엇을 여는가」에 아무도 답하지 못한다.
#:
#: ⚠️⚠️ **여기에 낱말을 추가하는 것은 보안 결정이다.** 모르는 낱말은 아무 행동도 열지 않는다
#:   (fail-closed) — 「비슷하니까 읽기겠지」로 넓히면 그 추측이 곧 권한이 된다.
MANIFEST_ACTION_WORDS: Dict[str, str] = {
    # 읽기
    "read": READ, "view": READ, "list": READ, "get": READ,
    # 쓰기 — 생성과 수정을 나누지 않는다(데이터 평면이 둘을 같은 행동으로 본다)
    "create": WRITE, "update": WRITE, "write": WRITE, "upsert": WRITE,
    # 삭제 — 논리 삭제도 삭제다
    "delete": DELETE, "remove": DELETE,
    # 구조 변경
    "manage": MANAGE, "admin": MANAGE, "schema": MANAGE,
}


def manifest_actions(manifest: Any) -> Tuple[str, ...]:
    """매니페스트 선언 → 정책 행동 집합.

    ★ 두 표기를 **모두** 읽는다(`core/app_manifest._normalize_capabilities` 와 같은 계약):
      `["material_plan.read"]` 그리고 `[{"resource":…, "actions":[…]}]`.
    ⚠️ 빈 결과는 «전부 허용» 이 아니라 **«데이터 행동을 선언하지 않은 앱»** 이다."""
    if not isinstance(manifest, dict):
        return ()
    out: List[str] = []

    for item in (manifest.get("required_capabilities") or []):
        if not isinstance(item, dict):
            continue
        for a in (item.get("actions") or []):
            act = MANIFEST_ACTION_WORDS.get(str(a).strip().lower())
            if act:
                out.append(act)

    for s in (manifest.get("capabilities") or []):
        if not isinstance(s, str):
            continue
        #: `resource.action` 의 뒷조각만 본다. 동작이 없는 선언(`"arrival"`)은 아무것도 열지
        #: 않는다 — `app_manifest` 가 「동작이 없으면 지어내지 않는다」고 못박은 것과 같다.
        word = s.rpartition(".")[2].strip().lower() if "." in s else ""
        act = MANIFEST_ACTION_WORDS.get(word)
        if act:
            out.append(act)

    return tuple(a for a in ACTIONS if a in set(out))     # 순서를 고정한다


def read_release(release_id: str) -> Optional[Dict[str, Any]]:
    """`release.json` 을 읽는다. 실패는 `None` — **«못 읽었으니 통과» 로 두지 않는다.**"""
    rid = str(release_id or "").strip()
    if not rid:
        return None
    try:
        from core import library_paths
        path = os.path.join(library_paths.release_dir(rid), "release.json")
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def resource_scope(release: Optional[Dict[str, Any]], release_id: str) -> app_policy.ResourceScope:
    """릴리스 → **범용 자원 범위**.

    ⚠️ 소유 축은 `ownership` 미러를 우선한다 — 기존 판정(`assert_release_*`)이 보는 바로 그
      값이다. 두 판정이 다른 사실을 보면 동등성 대조가 무의미해진다
      (`app_data_control._release_scope` 가 같은 이유로 그렇게 한다)."""
    if not isinstance(release, dict):
        return app_policy.ResourceScope(binding_state=app_policy.INVALID)
    own_dept = str(release.get("owner_dept_id", "") or "")
    own_user = str(release.get("owner_user_id", "") or "")
    try:
        from core.org_directory import org_directory
        mirror = org_directory.get_ownership("release", str(release_id or ""))
        if mirror:
            own_dept = str(mirror.get("dept_id", "") or "")
            own_user = str(mirror.get("owner_user_id", "") or "")
    except Exception:
        pass
    return app_policy.ResourceScope(
        tenant_id=str(release.get("tenant_id", "") or ""),
        entity_mode=str(release.get("entity_mode", "") or ""),
        scope_node_id=str(release.get("enterprise_scope_id", "") or ""),
        owner_user_id=own_user,
        owner_dept_id=own_dept,
        binding_state=app_policy.BOUND)


def app_facts(release: Optional[Dict[str, Any]], release_id: str) -> app_policy.AppResourceFacts:
    """릴리스 → **앱 전용 정책 사실**. 전부 서버가 만든다.

    ★ `app_id` 는 `project_id` 다. 릴리스는 «그 앱의 한 판» 이고 앱 자체의 이름은 프로젝트다 —
      새 식별자를 만들면 어느 쪽이 정본인지 곧 알 수 없게 된다.
    ⚠️ 매니페스트가 없는 옛 릴리스는 **빈 선언**이 된다. 그러면 `_manifest_ok` 가 막는다 —
      그것이 옳다(선언하지 않은 앱은 데이터를 만지지 못한다). `legacy_mode` 는 켜지 않는다:
      켜는 것은 «이 앱은 옛 앱이다» 를 사람이 판단해 명시하는 일이지 기본값이 아니다."""
    if not isinstance(release, dict):
        return app_policy.AppResourceFacts(release_id=str(release_id or ""))
    snap = release.get("manifest") or {}
    man = snap.get("manifest") if isinstance(snap, dict) else None
    return app_policy.AppResourceFacts(
        app_id=str(release.get("project_id", "") or ""),
        release_id=str(release_id or ""),
        app_class=str((man or {}).get("app_class", "") or release.get("app_class", "") or ""),
        manifest_fingerprint=str((snap or {}).get("fingerprint", "") or ""),
        manifest_version=str((man or {}).get("version", "") or ""),
        declared_capabilities=manifest_actions(man),
        legacy_mode=False)


def grantable_actions(subject: app_policy.Subject, res: app_policy.ResourceScope,
                      facts: app_policy.AppResourceFacts) -> Tuple[str, ...]:
    """★★★ 증명에 담을 행동 = **① 사용자가 실제로 할 수 있는 것 ∩ ② 매니페스트 선언**.

    ① 을 «판정기에게 물어서» 얻는 것이 요점이다. 여기서 부서·범위·문맥을 다시 계산하면
    판정이 두 곳이 되고, 두 곳은 반드시 언젠가 갈라진다.

    ⚠️ 물을 때는 **세션 주체**로 묻는다(`via="session"`). 아직 증명이 없는 시점이므로
      토큰 축을 켜면 «증명을 받으려면 증명이 필요한» 순환이 된다."""
    declared = set(facts.declared_capabilities or ())
    out: List[str] = []
    for action in ACTIONS:
        if action not in declared:
            continue
        d = app_policy.decide(subject, res, action, app=None)
        if d.allowed:
            out.append(action)
    return tuple(out)
