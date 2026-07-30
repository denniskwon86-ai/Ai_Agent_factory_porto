import io
import json
import zipfile

import pytest

from core.knowledge_base import DocumentExtractionError, extract_text
from core.reference_registry import build_registry


def _office_zip(parts: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, text in parts.items():
            zf.writestr(name, text)
    return out.getvalue()


def test_extract_docx_text_and_pptx_slide_and_notes():
    docx = _office_zip({"word/document.xml": '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>배터리 소재</w:t></w:r></w:p></w:body></w:document>'})
    pptx = _office_zip({
        "ppt/slides/slide1.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:t>생산 계획</a:t></p:sld>',
        "ppt/notesSlides/notesSlide1.xml": '<p:notes xmlns:p="p" xmlns:a="a"><a:t>승인 필요</a:t></p:notes>',
    })
    assert "배터리 소재" in extract_text("input.docx", docx)
    extracted = extract_text("input.pptx", pptx)
    assert "[[slide.1]]" in extracted
    assert "생산 계획" in extracted and "승인 필요" in extracted


def test_legacy_ppt_requires_safe_conversion():
    with pytest.raises(DocumentExtractionError):
        extract_text("legacy.ppt", b"not parsed as a presentation")


def test_reference_registry_scans_and_preserves_review_fields(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    (root / "배터리소재_SIOP_상세도입계획_v2.docx").write_bytes(b"docx-source")
    training = root / "전사교육자료"
    training.mkdir()
    (training / "16. 품질관리.pptx").write_bytes(b"pptx-source")
    (training / "legacy.ppt").write_bytes(b"ppt-source")
    target = tmp_path / "reference_registry.json"

    first = build_registry(root, target)
    assert first["summary"] == {"total": 3, "supported": 2, "conversion_required": 1, "pending_review": 3}
    battery = next(a for a in first["assets"] if "배터리" in a["filename"])
    assert battery["pack_id"] == "battery-materials-operations"
    battery["approval_status"] = "APPROVED"
    target.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")

    second = build_registry(root, target)
    battery_again = next(a for a in second["assets"] if "배터리" in a["filename"])
    assert battery_again["approval_status"] == "APPROVED"


# ══════════════════════════════════════════════════════════════════════════
# [2026-07-30] M2 범위 계약 연결 — 소유 파생 · 승인 문 · 색인 조건
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture()
def reg(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    (root / "배터리소재_SIOP.docx").write_bytes(b"docx")
    (root / "제련_원료수급.docx").write_bytes(b"docx")
    (root / "legacy.ppt").write_bytes(b"ppt")
    target = tmp_path / "reference_registry.json"
    return build_registry(root, target), target


def test_owner_is_derived_from_scope_code_not_left_blank(reg):
    """★★ 실측에서 자산 68건 전부 `owner_org_id` 가 공백이었는데 `scope_code` 는 채워져 있었다.

    같은 사실("이 자산은 누구 것인가")이 두 칸에 나뉘어 하나만 채워진 상태다. 관문 A 이후 빈
    소유는 **비노출**이므로, 빈 쪽을 읽는 소비자에게는 자산이 통째로 사라진다 — 라이브러리
    경로에서 닫은 것과 같은 유형의 중복이다."""
    from core.reference_registry import _owner_of
    first, _ = reg
    assert all(a["owner_org_id"] for a in first["assets"]), "소유가 빈 자산이 남아 있다"
    battery = next(a for a in first["assets"] if "배터리" in a["filename"])
    assert battery["owner_org_id"] == "MNM_BATTERY" == _owner_of(battery)


def test_explicit_owner_survives_rescan(reg):
    """★ 파생은 기본값일 뿐이다 — 사람이 명시 지정한 소유는 재스캔이 덮어쓰지 않는다."""
    first, target = reg
    a = first["assets"][0]
    a["owner_org_id"] = "MNM_COPPER_SPECIAL"
    target.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    again = build_registry(target.parent / "reference", target)
    assert again["assets"][0]["owner_org_id"] == "MNM_COPPER_SPECIAL"


def test_unapproved_asset_is_not_indexable(reg):
    """★★ 등록은 색인이 아니다 — 실측 68건이 전부 이 상태였다(승인 0 · 색인 0)."""
    from core.reference_registry import indexable
    _, target = reg
    out = indexable(target)
    assert out["total"] == 0
    assert out["blocked"]["not_approved"] == 3
    assert "승인 대기 3건" in out["note"]


def test_approval_opens_indexing_and_records_the_approver(reg):
    """★★ 색인은 되돌릴 수 없다(프롬프트에 실려 나간 산출물은 되돌아오지 않는다) —
    그래서 승인자를 반드시 남긴다."""
    from core.enterprise_context import audit
    from core.reference_registry import approve_asset, indexable
    first, target = reg
    battery = next(a for a in first["assets"] if "배터리" in a["filename"])

    out = approve_asset(battery["asset_id"], "cdo@ls", registry_path=target)
    assert out["approval_status"] == "APPROVED" and out["approved_by"] == "cdo@ls"
    assert out["approved_at"]

    idx = indexable(target)
    assert idx["total"] == 1 and idx["items"][0]["owner_org_id"] == "MNM_BATTERY"
    assert audit.recent(limit=1)[0]["event"] == audit.APPROVAL_GRANTED


def test_conversion_required_asset_is_never_indexable(reg):
    """★ 추출할 수 없는 파일을 승인해도 색인 대상이 아니다 — 빈 문서를 색인하면 검색은
    되는데 내용이 없다(가장 나쁜 상태다)."""
    from core.reference_registry import approve_asset, indexable
    first, target = reg
    legacy = next(a for a in first["assets"] if a["filename"] == "legacy.ppt")
    approve_asset(legacy["asset_id"], "cdo@ls", registry_path=target)
    out = indexable(target)
    assert out["total"] == 0 and out["blocked"]["conversion_required"] == 1


def test_approval_requires_an_owner(reg):
    """★★ 소유 없는 자산을 승인하면 **승인은 됐는데 아무에게도 안 보이는** 상태가 된다."""
    from core.reference_registry import approve_asset
    first, target = reg
    first["assets"][0]["owner_org_id"] = ""
    first["assets"][0]["scope_code"] = ""
    target.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="소유 조직이 없어 승인할 수 없습니다"):
        approve_asset(first["assets"][0]["asset_id"], "cdo@ls", registry_path=target)


def test_approver_identity_is_required(reg):
    from core.reference_registry import approve_asset
    first, target = reg
    with pytest.raises(ValueError, match="승인자 식별 정보가 없습니다"):
        approve_asset(first["assets"][0]["asset_id"], "", registry_path=target)


def test_rejection_requires_a_reason(reg):
    """★ 사유 없는 반려는 같은 문서가 계속 다시 올라오게 만든다."""
    from core.reference_registry import reject_asset
    first, target = reg
    aid = first["assets"][0]["asset_id"]
    with pytest.raises(ValueError, match="반려 사유는 필수"):
        reject_asset(aid, "cdo@ls", "", registry_path=target)
    out = reject_asset(aid, "cdo@ls", "개인정보 포함", registry_path=target)
    assert out["approval_status"] == "REJECTED" and out["approved_by"] == ""


def test_visible_assets_uses_the_single_scope_judgment(reg):
    """★★ 판정은 `scoping.filter_visible` 한 곳에 맡긴다 — 여기서 다시 구현하면 카탈로그·
    용어사전과 규칙이 어긋나고, 어긋난 권한 판정은 유출이거나 실명이다."""
    from core.reference_registry import visible_assets
    _, target = reg
    battery = visible_assets("MNM_BATTERY", registry_path=target)
    assert [a["filename"] for a in battery] == ["배터리소재_SIOP.docx"]

    copper = visible_assets("MNM_COPPER", registry_path=target)
    names = [a["filename"] for a in copper]
    assert "제련_원료수급.docx" in names and "배터리소재_SIOP.docx" not in names

    # 범위를 주지 않으면 필터하지 않는다(ECM 미도입 흐름 보호).
    assert len(visible_assets(registry_path=target)) == 3


def test_summary_says_why_the_knowledge_pack_is_empty(reg):
    """★★ 등록 건수만 주면 "68건 등록됐는데 지식팩이 왜 비었나"를 아무도 설명할 수 없다."""
    from core.reference_registry import registry_summary
    _, target = reg
    s = registry_summary(target)
    assert s["total"] == 3 and s["approved"] == 0 and s["indexable"] == 0
    assert s["unscoped"] == 0, "소유 파생 이후에는 미지정이 없어야 한다"
    assert "등록은 색인이 아닙니다" in s["note"]


def test_reference_routes_are_reachable():
    """★ 라우터에 승인 경로가 없으면 등록부는 영원히 PENDING_REVIEW 로 남는다."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    assert c.get("/api/v1/reference/indexable").status_code != 404
    # 승인 라우트는 존재해야 한다(자산이 없으면 400 — 404 가 아니다).
    r = c.post("/api/v1/reference/assets/REF-NOPE/approve", json={})
    assert r.status_code != 404
