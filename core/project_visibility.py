"""★★★ [G1-C] 프로젝트 가시성 판정 — **한 곳에서만 답한다.**

## 왜 `api/routes/factory_control.py` 에서 옮겼는가

이 규칙은 원래 라우트 파일 안의 사설 함수였다. 목록 API 만 쓰던 동안은 그래도 됐다.
G1-C 로 **SSE 이벤트도 같은 질문을 하게 되면서** 사정이 달라졌다 —
「이 프로젝트가 이 사람에게 보이는가」에 두 곳이 각자 답하기 시작하면,
목록에서는 안 보이는 프로젝트의 진행 이벤트가 실시간으로 흘러드는 상태가 만들어진다.
그리고 그 어긋남은 **조용하다.** 아무도 오류를 보지 못한다.

이 저장소는 같은 실수를 이미 겪었다(`api/deps._enforced` 주석: 「이걸 함수마다 따로
확인하면 어긋난다 — 실제로 어긋났다」). 그래서 규칙을 `core/` 로 올리고 라우트는 위임한다.

## ⚠️ 미기록 소유권을 막지 않는 이유

마이그레이션 전 프로젝트에는 소유 부서가 없다. 그것을 «비공개» 로 읽으면 기존 프로젝트가
전부 사라져 기능이 통째로 멈춘다. 하위호환이 우선이라는 판단은 원본 그대로 유지한다.
**이 파일은 규칙을 옮기는 것이지 바꾸는 것이 아니다** — 규칙을 옮기면서 함께 바꾸면
어느 쪽이 원인인지 나중에 가릴 수 없다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


def project_meta_path(workspace_root: str) -> str:
    return os.path.join(workspace_root, "project_meta.json")


def read_project_ownership(workspace_root: str) -> Dict[str, Any]:
    """소유권 필드만 별도로 읽는다 (설계서 Phase 3).

    ⚠️ `_read_project_meta` 의 3-튜플 반환은 **바꾸지 않는다** — 호출부가 많아 시그니처를
      건드리면 전 경로가 깨진다. `_read_project_packs` 와 같은 패턴으로 따로 뽑는다."""
    try:
        with open(project_meta_path(workspace_root), "r", encoding="utf-8") as f:
            d = json.load(f) or {}
    except Exception:
        d = {}
    return {
        "owner_dept_id": str(d.get("owner_dept_id", "") or ""),
        "owner_user_id": str(d.get("owner_user_id", "") or ""),
        "visibility": str(d.get("visibility", "dept") or "dept"),
        "nature": str(d.get("nature", "") or ""),
        "forked_from": d.get("forked_from") or {},
        # [ECM-lite] 설계서 §10.2 "프로젝트는 반드시 enterprise_scope_id 와 entity_mode 를
        #   소유한다". 구 프로젝트는 기본값(기본 테넌트 · 실제 문맥)으로 읽는다.
        "tenant_id": str(d.get("tenant_id", "") or "tenant_default"),
        "enterprise_scope_id": str(d.get("enterprise_scope_id", "") or ""),
        "entity_mode": str(d.get("entity_mode", "") or "REAL"),
        "blueprint_id": str(d.get("blueprint_id", "") or ""),
    }


def ownership_visible(scope, user_id: str, own: Optional[Dict[str, Any]]) -> bool:
    """이 소유권 정보를 가진 자원이 이 사람에게 보이는가 (예외를 던지지 않는 목록 필터용).

    ⚠️ 소유권이 **미기록**인 자원은 막지 않는다. 마이그레이션 전 기존 프로젝트가
      전부 안 보이게 되면 기능이 통째로 멈춘다 — 하위호환이 우선이다.

    ★ `Principal` 이 아니라 `(scope, user_id)` 를 받는다. `core/` 가 `api/` 의 타입을 알면
      의존 방향이 뒤집히고, SSE 브로드캐스터처럼 **요청 밖에서** 판정해야 하는 호출자가
      Principal 을 만들 수 없다."""
    try:
        if scope is None or scope.unrestricted:
            return True
    except Exception:
        return True
    own = own or {}
    dept = own.get("owner_dept_id", "")
    vis = own.get("visibility", "dept")
    if not dept and not own.get("owner_user_id"):
        return True                       # 미기록 = 무소속 → 하위호환
    if vis == "company":
        return True
    if own.get("owner_user_id") and own["owner_user_id"] == user_id:
        return True
    return bool(dept) and dept in scope.readable_dept_ids


def user_can_see_project(user_id: str, project_id: str) -> bool:
    """[G1-C] **요청 밖에서** 쓰는 편의 판정 — SSE 이벤트 배달용.

    ⚠️ 권한(scope)을 **부를 때마다 다시 해석한다.** 구독 시점에 굳혀 두면 안 된다 —
      SSE 연결은 12시간까지 살아 있고, 그 사이 권한을 회수해도 이미 열린 스트림으로는
      계속 흘러간다. `api/deps` 가 세션 토큰에 권한을 담지 않는 이유와 같다
      (「토큰에 권한을 담으면 회수해도 토큰이 사는 동안 유효해진다」).
      `resolve_scope` 는 캐시되고 조직 쓰기 시 무효화되므로 매번 부르는 비용은 작다.

    ⚠️ 판정에 필요한 것을 못 읽으면 **보이지 않는 쪽**으로 답한다. 실패가 노출로 이어지면
      안 된다 — 다만 «소유권 미기록» 은 실패가 아니라 하위호환이며 위에서 통과시킨다."""
    pid = (project_id or "").strip()
    if not pid:
        return False
    try:
        from core.org_directory import org_directory
        from core.paths import workspace_path
        scope = org_directory.resolve_scope((user_id or "").strip())
        if getattr(scope, "unrestricted", False):
            return True
        return ownership_visible(scope, (user_id or "").strip(),
                                 read_project_ownership(workspace_path(pid)))
    except Exception:
        return False
