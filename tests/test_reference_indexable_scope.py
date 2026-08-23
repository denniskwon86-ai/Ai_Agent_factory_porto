# -*- coding: utf-8 -*-
"""★★★ `/reference/indexable` 의 **조직 범위** — 주석이 약속한 통제가 실제로 있는가.

## 무엇을 잡는 시험인가 (2026-08-23 실측)

라우트 주석은 「이 응답은 문서 파일명을 그대로 담는다 — 집계만 담는 `/summary` 와 달리
**목록 통제를 적용한다**」고 적어 두었다. 그런데 코드가 부르는 것은
`visibility_block_reason(p)` 하나였고, 그것은 「이 사람이 **아무것도** 못 보는가」를 묻는
전역 관문이지 범위 필터가 아니다.

실측 결과:

    제련공장 소속 일반 계정 → `/reference/assets`    **0건**
                          → `/reference/indexable` 관리자와 **완전히 같은 응답**
                            (자산 ID · 파일 경로 · `approved_by` 이름 포함)

★ 같은 영역에서 **목록은 막고 색인은 안 막았다.** 통제를 한 곳에서만 지운 전형이다.

⚠️ 이 시험은 「응답이 200 인가」를 보지 않는다. 200 은 둘 다 받는다 — **내용이 갈리는가**를
  본다. 「관리자도 200, 일반도 200」은 통과가 아니다.
⚠️ 「둘 다 0건」으로 초록이 되지 않게 **관리자 쪽이 실제로 무언가를 보는 것**을 먼저 단언한다.
  빈 것과 빈 것이 같은 건 아무것도 증명하지 않는다.
"""
import json

import pytest

from core.reference_registry import indexable


def _registry(tmp_path, rows):
    """⚠️ `registry_version` 을 **정본과 같게** 적는다. 다르면 `load_registry` 가
      「판정 버전이 다르다」며 파일시스템을 다시 스캔해 **이 fixture 를 통째로 버린다**
      (1차 시도가 그래서 «0건» 으로 초록도 빨강도 아닌 답을 냈다)."""
    from core.reference_registry import REGISTRY_VERSION
    p = tmp_path / "registry.json"
    p.write_text(json.dumps({"registry_version": REGISTRY_VERSION, "assets": rows},
                            ensure_ascii=False), encoding="utf-8")
    return p


def _asset(aid, scope, *, approved=True):
    """⚠️ 칸 이름을 **내 말로 짓지 않는다.** 1차 시도에서 `owner_scope_node_id` ·
      `extraction_status="EXTRACTED"` 로 지어냈더니 `indexable()` 이 **0건**을 돌려줬고,
      그 0은 «통제가 먹었다» 처럼 보였다. 정본이 실제로 읽는 칸은:

          소유 조직 → `_owner_of()` = `owner_org_id` 또는 `scope_code`
          추출 가능 → `extraction_status == "SUPPORTED"`
          승인      → `approval_status == "APPROVED"`
    """
    return {
        "asset_id": aid,
        "relative_path": f"{scope}/{aid}.docx",
        "pack_id": "pack-a",
        "owner_org_id": scope,
        "scope_code": scope,
        "approval_status": "APPROVED" if approved else "PENDING_REVIEW",
        "approved_by": "hikwon@lsmnm.com",
        "extraction_status": "SUPPORTED",
        "classification": "INTERNAL",
    }


@pytest.fixture()
def two_orgs(tmp_path):
    """서로 다른 조직의 자산 둘. ★ 한쪽만 보이는 상황을 만들 수 있어야 시험이 성립한다."""
    return _registry(tmp_path, [_asset("REF-HQ-1", "corp-afs"),
                                _asset("REF-PLANT-1", "plant-afs-smelting-01")])


def _ids(result):
    return sorted(i["asset_id"] for i in (result.get("items") or []))


def test_no_scope_means_no_filter_backward_compatible(two_orgs):
    """`None` 은 «필터하지 않는다» — ECM 미도입 흐름의 하위호환 계약이다.

    ⚠️ 이 값을 «아무것도 안 보인다» 로 바꾸면 조직을 도입하지 않은 설치가 통째로 막힌다."""
    out = indexable(two_orgs, visible_scope_nodes=None)
    assert _ids(out) == ["REF-HQ-1", "REF-PLANT-1"]
    #: ★ 대조군이 실제로 «무언가 보이는» 상태임을 먼저 확정한다 — 아래 시험들이 «0 vs 0» 으로
    #:   거짓 초록이 되지 않게 한다.
    assert out["total"] == 2


def test_empty_scope_set_means_nothing_visible(two_orgs):
    """빈 집합은 «볼 수 있는 범위가 없다» 다. `None` 과 **같게 다루면 통제가 사라진다.**"""
    out = indexable(two_orgs, visible_scope_nodes=set())
    assert _ids(out) == []
    assert out["total"] == 0


def test_scope_filters_to_own_org(two_orgs):
    """자기 조직 자산만 나온다 — 남의 조직 자산의 **ID 도 경로도** 나오지 않는다."""
    out = indexable(two_orgs, visible_scope_nodes={"plant-afs-smelting-01"})
    assert _ids(out) == ["REF-PLANT-1"]
    #: ⚠️ 건수만 세지 않는다. 파일 경로에 조직명이 들어가므로 **본문 전체**에 남의 값이
    #:   섞이지 않았는지 본다(라우트 주석이 「파일명 자체가 정보다」라고 적은 이유).
    assert "corp-afs" not in json.dumps(out, ensure_ascii=False)
    assert "REF-HQ-1" not in json.dumps(out, ensure_ascii=False)


def test_two_scopes_see_different_things(two_orgs):
    """★ 범위가 다르면 **답이 갈려야** 한다. 갈리지 않으면 통제가 없는 것이다."""
    hq = indexable(two_orgs, visible_scope_nodes={"corp-afs"})
    plant = indexable(two_orgs, visible_scope_nodes={"plant-afs-smelting-01"})
    assert _ids(hq) != _ids(plant)
    assert _ids(hq) == ["REF-HQ-1"]
    assert _ids(plant) == ["REF-PLANT-1"]


def test_blocked_counts_are_also_scoped(tmp_path):
    """막힌 건수도 자기 범위 것만 센다.

    ⚠️ 건수만 전사로 새면 「우리 조직에 승인 대기 51건」처럼 **남의 조직 규모**를 알려 준다."""
    reg = _registry(tmp_path, [_asset("A", "corp-afs", approved=False),
                               _asset("B", "corp-afs", approved=False),
                               _asset("C", "plant-afs-smelting-01", approved=False)])
    out = indexable(reg, visible_scope_nodes={"plant-afs-smelting-01"})
    assert out["blocked"]["not_approved"] == 1, out["blocked"]
