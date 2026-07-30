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
    # ★ 실제 OOXML(zip)로 만든다 — 확장자만 맞는 바이트는 이제 CONVERSION_REQUIRED 로 잡힌다
    #   (아래 `test_extension_alone_does_not_mean_extractable` 가 그 판정을 검증한다).
    (root / "배터리소재_SIOP_상세도입계획_v2.docx").write_bytes(
        _office_zip({"word/document.xml":
                     '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>SIOP</w:t>'
                     '</w:r></w:p></w:body></w:document>'}))
    training = root / "전사교육자료"
    training.mkdir()
    (training / "16. 품질관리.pptx").write_bytes(
        _office_zip({"ppt/slides/slide1.xml":
                     '<p:sld xmlns:p="p" xmlns:a="a"><a:t>품질</a:t></p:sld>'}))
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
    # 실제 OOXML(zip)로 만든다 — 확장자만 맞는 바이트는 CONVERSION_REQUIRED 로 잡혀 색인
    #   대상에서 빠지므로, 승인·색인 경로를 검증하려면 열리는 파일이어야 한다.
    (root / "배터리소재_SIOP.docx").write_bytes(_docx("배터리 SIOP"))
    (root / "제련_원료수급.docx").write_bytes(_docx("동제련 원료"))
    (root / "legacy.ppt").write_bytes(b"ppt")
    target = tmp_path / "reference_registry.json"
    return build_registry(root, target), target


def test_extension_alone_does_not_mean_extractable(tmp_path):
    """★★ [2026-07-30 실측] 확장자만 보고 `SUPPORTED` 로 판정하면 현실을 4배 과대평가한다.

    실제 등록부에서 `SUPPORTED` 67건 중 **열리는 것은 16건**이었다 — 51건이 확장자만
    `.pptx`/`.docx` 인 레거시 바이너리(`.ppt`/`.doc` 를 이름만 바꾼 파일)였다.

    ⚠️ 이건 부정확한 숫자가 아니라 **거짓 약속**이다. 사람이 68건을 승인하고 "지식팩에 68건이
      들어갔다"고 믿게 되는데 실제로는 16건이고, 그러면 답변 품질이 왜 낮은지 아무도 설명할 수
      없다."""
    root = tmp_path / "reference"
    root.mkdir()
    (root / "진짜.docx").write_bytes(_docx("내용 있음"))
    (root / "이름만_docx.docx").write_bytes(b"\xd0\xcf\x11\xe0 legacy OLE binary")
    (root / "이름만_pdf.pdf").write_bytes(b"not a pdf at all")
    (root / "메모.md").write_text("마크다운은 시그니처가 없다", encoding="utf-8")
    target = tmp_path / "reg.json"

    out = build_registry(root, target)
    st = {a["filename"]: a["extraction_status"] for a in out["assets"]}
    assert st["진짜.docx"] == "SUPPORTED"
    assert st["이름만_docx.docx"] == "CONVERSION_REQUIRED", "레거시 바이너리가 SUPPORTED 로 잡혔다"
    assert st["이름만_pdf.pdf"] == "CONVERSION_REQUIRED"
    assert st["메모.md"] == "SUPPORTED", "시그니처 없는 텍스트 형식을 막으면 안 된다"
    assert out["summary"]["supported"] == 2 and out["summary"]["conversion_required"] == 2


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


# ── 색인 실행 (2026-07-30) ──────────────────────────────────────────────────
class _FakeKB:
    """지식팩 대역. chromadb 없이도 색인 계약을 검증한다 — 메타데이터가 청크에 실리는지가
    핵심이므로 저장소 구현이 아니라 **호출 계약**을 본다."""

    def __init__(self, fail_on: str = ""):
        self.calls: list[dict] = []
        self.fail_on = fail_on

    def add_document(self, pack_id, filename, text, source="upload", raw=None,
                     extra_meta=None):
        if self.fail_on and self.fail_on in filename:
            raise ValueError("임베딩 저장소 오류(테스트)")
        self.calls.append({"pack_id": pack_id, "filename": filename, "text": text,
                           "source": source, "extra_meta": extra_meta or {}})
        return 3


def _docx(text: str) -> bytes:
    return _office_zip({"word/document.xml":
                        f'<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>{text}</w:t>'
                        f'</w:r></w:p></w:body></w:document>'})


@pytest.fixture()
def indexed_env(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    (root / "배터리소재_SIOP.docx").write_bytes(_docx("배터리 SIOP 운영 기준"))
    target = tmp_path / "reference_registry.json"
    reg = build_registry(root, target)
    from core.reference_registry import approve_asset
    aid = reg["assets"][0]["asset_id"]
    approve_asset(aid, "cdo@ls", registry_path=target)
    return root, target, aid


def test_dry_run_indexes_nothing(indexed_env):
    """★★ 색인은 되돌릴 수 없다 — 프롬프트에 실려 나간 산출물은 지워도 돌아오지 않는다.
    그래서 예행이 기본이다."""
    from core.reference_registry import index_approved, load_registry
    root, target, _ = indexed_env
    kb = _FakeKB()
    out = index_approved(root, target, dry_run=True, kb=kb)

    assert out["indexed"] == 1 and out["dry_run"] is True and kb.calls == []
    assert "[예행]" in out["note"]
    assert load_registry(target)["assets"][0]["ingestion_status"] == "REGISTERED"


def test_real_index_carries_org_scope_into_the_chunks(indexed_env):
    """★★ 색인하면서 범위를 심지 않으면, 등록부에서 통제한 문서가 색인되는 **순간 통제 밖으로
    나간다.** 색인은 통제의 끝이 아니라 통제가 따라가야 하는 지점이다."""
    from core.reference_registry import index_approved, load_registry
    root, target, _ = indexed_env
    kb = _FakeKB()
    out = index_approved(root, target, dry_run=False, kb=kb)

    assert out["indexed"] == 1 and out["failed"] == 0
    call = kb.calls[0]
    assert call["pack_id"] == "battery-materials-operations"
    assert call["source"] == "reference-registry"
    assert "배터리 SIOP 운영 기준" in call["text"]
    assert call["extra_meta"]["owner_org_id"] == "MNM_BATTERY"
    assert call["extra_meta"]["classification"] == "INTERNAL"
    assert call["extra_meta"]["approved_by"] == "cdo@ls"

    asset = load_registry(target)["assets"][0]
    assert asset["ingestion_status"] == "INDEXED" and asset["indexed_chunks"] == 3
    assert asset["indexed_sha256"] == asset["sha256"]


def test_reindex_is_skipped_when_content_is_unchanged(indexed_env):
    """★ 같은 내용을 다시 넣지 않는다 — 임베딩은 비용이고 시간이다."""
    from core.reference_registry import index_approved
    root, target, _ = indexed_env
    kb = _FakeKB()
    index_approved(root, target, dry_run=False, kb=kb)
    again = index_approved(root, target, dry_run=False, kb=kb)

    assert again["indexed"] == 0 and again["skipped"] == 1
    assert "이미 색인됨" in again["skipped_items"][0]["reason"]
    assert len(kb.calls) == 1, "같은 내용이 두 번 색인됐다"


def test_changed_file_is_reindexed(indexed_env):
    """★★ 파일이 바뀌면 다시 넣는다 — 낡은 내용이 프롬프트에 계속 실리면 그게 오답의 근거가 된다."""
    from core.reference_registry import index_approved
    root, target, _ = indexed_env
    kb = _FakeKB()
    index_approved(root, target, dry_run=False, kb=kb)

    (root / "배터리소재_SIOP.docx").write_bytes(_docx("개정된 SIOP 기준"))
    build_registry(root, target)          # 재스캔 → sha256 변경(승인은 보존)
    out = index_approved(root, target, dry_run=False, kb=kb)

    assert out["indexed"] == 1 and len(kb.calls) == 2
    assert "개정된 SIOP 기준" in kb.calls[1]["text"]


def test_unapproved_asset_is_never_indexed(indexed_env):
    """★★ 승인 없는 문서는 색인되지 않는다 — 색인은 승인의 결과여야 한다."""
    from core.reference_registry import index_approved, reject_asset
    root, target, aid = indexed_env
    reject_asset(aid, "cdo@ls", "개인정보 포함", registry_path=target)
    kb = _FakeKB()
    out = index_approved(root, target, dry_run=False, kb=kb)
    assert out["indexed"] == 0 and kb.calls == []


def test_missing_source_file_is_reported_not_silent(indexed_env):
    """★ 등록 후 파일이 사라졌으면 그 사실을 말한다 — 조용히 0건이면 "색인이 고장났다"가 된다."""
    from core.reference_registry import index_approved
    root, target, _ = indexed_env
    (root / "배터리소재_SIOP.docx").unlink()
    out = index_approved(root, target, dry_run=False, kb=_FakeKB())
    assert out["failed"] == 1 and "원본 파일이 없습니다" in out["failed_items"][0]["reason"]


def test_indexing_failure_is_recorded_and_stops_the_empty_promise(indexed_env):
    """★★ [2026-07-30 실측] 실패를 기록하지 않으면 `indexable()` 이 계속 "색인 가능"이라고
    **지킬 수 없는 약속**을 반복하고, 운영자는 매번 같은 실패를 다시 본다.

    실제 등록부의 `.docx` 파일이 zip 이 아니어서 열리지 않았다 — `extraction_status` 는
    **확장자만** 보고 SUPPORTED 로 판정하기 때문이다.
    ⚠️ 그렇다고 `INDEXED` 로 적지도 않는다. 실패한 색인을 성공으로 적으면 그 문서가 지식팩에
      있다고 믿게 된다."""
    from core.reference_registry import index_approved, indexable, load_registry
    root, target, _ = indexed_env
    out = index_approved(root, target, dry_run=False, kb=_FakeKB(fail_on="배터리"))
    assert out["indexed"] == 0 and out["failed"] == 1
    assert "임베딩 저장소 오류" in out["failed_items"][0]["reason"]

    asset = load_registry(target)["assets"][0]
    assert asset["ingestion_status"] == "EXTRACTION_FAILED"
    assert asset["extraction_error"] and asset["extraction_failed_at"]

    idx = indexable(target)
    assert idx["total"] == 0 and idx["blocked"]["extraction_failed"] == 1
    assert "추출 실패 1건" in idx["note"]


def test_force_retries_a_previously_failed_asset(indexed_env):
    """★ 실패 기록이 **영구 사망 선고**가 되면 안 된다 — 파일을 변환해 올린 뒤 재시도할 길이
    있어야 한다."""
    from core.reference_registry import index_approved
    root, target, _ = indexed_env
    index_approved(root, target, dry_run=False, kb=_FakeKB(fail_on="배터리"))

    kb = _FakeKB()          # 이번에는 성공하는 대역(=변환 후 재시도)
    out = index_approved(root, target, dry_run=False, kb=kb, force=True)
    assert out["indexed"] == 1 and len(kb.calls) == 1


def test_empty_extraction_is_not_indexed(tmp_path):
    """★★ 빈 문서를 색인하면 검색은 되는데 내용이 없다 — 가장 나쁜 상태다."""
    from core.reference_registry import approve_asset, index_approved
    root = tmp_path / "reference"
    root.mkdir()
    (root / "빈문서.txt").write_bytes(b"   \n  ")
    target = tmp_path / "reg.json"
    reg = build_registry(root, target)
    approve_asset(reg["assets"][0]["asset_id"], "cdo@ls", registry_path=target)

    out = index_approved(root, target, dry_run=False, kb=_FakeKB())
    assert out["indexed"] == 0 and out["failed"] == 1
    assert "비어 있습니다" in out["failed_items"][0]["reason"]


def test_reference_routes_are_reachable():
    """★ 라우터에 승인 경로가 없으면 등록부는 영원히 PENDING_REVIEW 로 남는다."""
    from fastapi.testclient import TestClient
    import main

    c = TestClient(main.app)
    assert c.get("/api/v1/reference/indexable").status_code != 404
    # 승인 라우트는 존재해야 한다(자산이 없으면 400 — 404 가 아니다).
    r = c.post("/api/v1/reference/assets/REF-NOPE/approve", json={})
    assert r.status_code != 404


def test_stale_judgment_version_triggers_a_rescan(tmp_path):
    """★★ [2026-07-30 실측] 판정 의미가 바뀌었는데 버전을 올리지 않으면, 옛 판정이 **영구히**
    살아남는다.

    브라우저로 API 를 확인하다 발견했다 — `/reference/summary` 가 `supported: 67` 을 보고하는데
    실제로 열리는 것은 16건이었다. 저장된 1.0 파일이 확장자 기준 판정을 들고 있었기 때문이다.
    숫자가 틀린 것에서 끝나지 않는다: 그 숫자를 보고 67건을 승인하면 "지식팩에 67건이 들어갔다"고
    믿게 된다."""
    import json as _json
    from core.reference_registry import REGISTRY_VERSION, load_registry

    root = tmp_path / "reference"
    root.mkdir()
    (root / "이름만_docx.docx").write_bytes(b"\xd0\xcf\x11\xe0 legacy")
    target = tmp_path / "reg.json"

    # 옛 버전 + 옛 판정(확장자 기준이라 SUPPORTED)으로 위조한 등록부.
    stale = build_registry(root, target)
    stale["registry_version"] = "1.0"
    stale["assets"][0]["extraction_status"] = "SUPPORTED"
    stale["assets"][0]["approval_status"] = "APPROVED"       # 사람이 넣은 결정
    stale["assets"][0]["approved_by"] = "cdo@ls"
    target.write_text(_json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    fresh = load_registry(target, reference_root=root)
    assert fresh["registry_version"] == REGISTRY_VERSION
    assert fresh["assets"][0]["extraction_status"] == "CONVERSION_REQUIRED", \
        "옛 판정이 그대로 살아남았다"
    # ★ 사람이 넣은 결정은 재스캔에도 보존된다 — 안 그러면 아무도 재스캔을 신뢰하지 않는다.
    assert fresh["assets"][0]["approval_status"] == "APPROVED"
    assert fresh["assets"][0]["approved_by"] == "cdo@ls"


def test_same_version_is_not_rescanned(tmp_path):
    """★ 매번 재스캔하면 68건 해시 계산이 반복돼 API 가 느려진다 — 버전이 같으면 그대로 쓴다."""
    from core.reference_registry import load_registry

    root = tmp_path / "reference"
    root.mkdir()
    (root / "메모.md").write_text("내용", encoding="utf-8")
    target = tmp_path / "reg.json"
    first = build_registry(root, target)

    (root / "나중에추가.md").write_text("새 파일", encoding="utf-8")
    again = load_registry(target, reference_root=root)
    assert again["total"] if "total" in again else True
    assert len(again["assets"]) == len(first["assets"]) == 1, "버전이 같은데 재스캔됐다"
