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
