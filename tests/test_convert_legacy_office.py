"""[2026-07-30] 레거시 Office(OLE2) 변환 스크립트.

실측 배경: `docs/reference` 68건 중 **51건이 OLE2 레거시 바이너리**였다(확장자는 `.pptx`).
그래서 지식팩에 들어갈 수 있는 지식이 실제로는 1/4이었다.

이 파일이 잠그는 것:
  · **확장자를 믿지 않는다** — 실제 시그니처로 판정한다(그게 문제의 원인이었다)
  · **원본을 지우거나 덮어쓰지 않는다** — 원본은 증적이고 변환은 손실이 있을 수 있다
  · 예행이 기본
  · **변환기가 없으면 "성공"이라고 하지 않는다** — 할 일을 정확히 알려준다
  · 이미 변환된 파일은 다시 만들지 않는다
  · 한 건의 실패가 배치를 죽이지 않는다
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.convert_legacy_office import OLE2_MAGIC, is_ole2, plan, run

_MODERN_ZIP = b"PK\x03\x04rest-of-a-real-pptx"


@pytest.fixture()
def refs(tmp_path):
    root = tmp_path / "reference"
    root.mkdir()
    # 확장자는 최신인데 내용은 레거시 — 실제 등록부에서 51건이 이 상태였다.
    (root / "교재.pptx").write_bytes(OLE2_MAGIC + b"legacy ppt body")
    (root / "지침.docx").write_bytes(OLE2_MAGIC + b"legacy doc body")
    # 진짜 최신 형식 — 변환 대상이 아니다.
    (root / "정상.pptx").write_bytes(_MODERN_ZIP)
    # 확장자도 레거시
    (root / "구자료.ppt").write_bytes(OLE2_MAGIC + b"older")
    return root


def test_signature_decides_not_extension(refs):
    """★★ 확장자를 믿으면 51건을 '변환 불필요'로 오판한다 — 그게 원래 문제였다."""
    assert is_ole2(refs / "교재.pptx") is True
    assert is_ole2(refs / "정상.pptx") is False
    assert is_ole2(refs / "없는파일.pptx") is False


def test_plan_targets_only_legacy_files(refs):
    items = plan(refs, None)
    names = sorted(Path(i["source"]).name for i in items)
    assert names == ["교재.pptx", "구자료.ppt", "지침.docx"]
    assert "정상.pptx" not in names

    by = {Path(i["source"]).name: i for i in items}
    assert by["교재.pptx"]["app"] == "powerpoint"
    assert by["지침.docx"]["app"] == "word"
    # 변환본은 **새 파일**이다 — 원본을 덮어쓰는 경로를 만들지 않는다.
    assert Path(by["교재.pptx"]["target"]).name == "교재_converted.pptx"


def test_dry_run_is_the_default_and_writes_nothing(refs):
    out = run(refs, None)
    assert out["applied"] is False and out["converted"] == 3
    assert "[예행]" in out["note"]
    assert not list(refs.glob("*_converted*")), "예행인데 파일이 생겼다"


def test_apply_creates_new_files_and_keeps_originals(refs):
    """★★ 원본은 증적이다. 변환은 손실이 있을 수 있으므로 **원본을 지우지 않는다.**"""
    def _fake(item):
        Path(item["target"]).write_bytes(_MODERN_ZIP)
        return Path(item["target"])

    before = {p.name: p.read_bytes() for p in refs.iterdir()}
    out = run(refs, None, apply=True, converter=_fake)

    assert out["converted"] == 3 and out["failed"] == 0
    assert (refs / "교재_converted.pptx").exists()
    for name, data in before.items():
        assert (refs / name).read_bytes() == data, f"원본이 바뀌었다: {name}"


def test_already_converted_files_are_not_redone(refs):
    (refs / "교재_converted.pptx").write_bytes(_MODERN_ZIP)
    out = run(refs, None)
    sources = [Path(i["source"]).name for i in out["items"]]
    assert "교재.pptx" not in sources and out["planned"] == 3 and out["pending"] == 2


def test_limit_splits_the_batch(refs):
    """★ Office COM 백엔드는 앱을 띄우므로 느리다 — 나눠 돌릴 수 있어야 한다."""
    out = run(refs, None, limit=1)
    assert out["converted"] == 1 and out["pending"] == 1


def test_one_failure_does_not_kill_the_batch(refs):
    def _flaky(item):
        if "지침" in Path(item["source"]).name:
            raise RuntimeError("Office 가 파일을 열지 못했습니다")
        Path(item["target"]).write_bytes(_MODERN_ZIP)
        return Path(item["target"])

    out = run(refs, None, apply=True, converter=_flaky)
    assert out["converted"] == 2 and out["failed"] == 1
    assert "열지 못했습니다" in out["failed_items"][0]["reason"]


def test_no_converter_is_reported_not_faked(refs, monkeypatch):
    """★★ 변환기가 없는데 "성공"이라고 하면, 아무도 변환되지 않은 채로 넘어간다."""
    import scripts.convert_legacy_office as mod
    monkeypatch.setattr(mod, "detect_backend", lambda: (None, ""))

    out = mod.run(refs, None, apply=True)
    assert out["converted"] == 0 and out["backend"] is None
    assert "변환기를 찾지 못했습니다" in out["note"]
    assert "다른 이름으로 저장" in out["note"], "할 일을 알려주지 않으면 막다른 길이다"


def test_registry_is_used_as_the_single_judgment_when_present(refs, tmp_path):
    """★ 같은 판정(무엇이 변환 대상인가)을 두 곳에서 하면 어긋난다 — 등록부를 우선한다."""
    from core.reference_registry import build_registry
    reg_path = tmp_path / "reg.json"
    build_registry(refs, reg_path)

    items = plan(refs, reg_path)
    names = sorted(Path(i["source"]).name for i in items)
    assert names == ["교재.pptx", "구자료.ppt", "지침.docx"]


def test_rescan_reports_registry_state_after_conversion(refs, tmp_path):
    """★ 변환했다고 끝이 아니다 — 등록부의 `extraction_status` 가 실제로 바뀌었는지 본다."""
    from core.reference_registry import build_registry
    reg_path = tmp_path / "reg.json"
    before = build_registry(refs, reg_path)
    assert before["summary"]["supported"] == 1        # 정상.pptx 만

    def _fake(item):
        Path(item["target"]).write_bytes(_MODERN_ZIP)
        return Path(item["target"])

    out = run(refs, reg_path, apply=True, rescan=True, converter=_fake)
    assert out["registry_after"]["supported"] == 4, out["registry_after"]
    assert out["registry_after"]["total"] == 7       # 원본 4 + 변환본 3


def test_legacy_named_copy_avoids_the_extension_mismatch_prompt(refs):
    """★★ [2026-07-30 실측] Office 자동화가 멈춘 **진짜 원인**이 이것이었다.

    `.doc` 를 `.docx` 로 이름만 바꾼 파일을 열면 Word 가 "파일 형식과 확장자가 일치하지
    않습니다" **보안 프롬프트**를 띄운다. 이건 `DisplayAlerts=0` 으로 꺼지지 않고(보안 경고는
    알림이 아니다) 자동화는 그 앞에서 무한정 멈춘다. 그래서 실제 형식의 이름으로 사본을 만든다.

    ⚠️ 사본이므로 원본은 이름도 내용도 그대로여야 한다."""
    from scripts.convert_legacy_office import _legacy_named_copy

    src = refs / "교재.pptx"
    before = src.read_bytes()
    tmp = _legacy_named_copy(src)
    try:
        assert tmp is not None and tmp.suffix == ".ppt", "실제 형식 확장자로 열어야 한다"
        assert tmp.read_bytes() == before
        assert src.exists() and src.read_bytes() == before, "원본이 바뀌었다"
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


def test_stale_temp_copies_are_cleaned_on_next_run(refs):
    """★ 멈춘 Office 가 임시 사본을 붙잡으면 unlink 가 실패해 잔여물이 남는다(실측).
    쌓이면 다음 스캔이 그것들까지 자산으로 센다."""
    stale = refs / ".교재__legacy_tmp.ppt"
    stale.write_bytes(OLE2_MAGIC + b"leftover")
    run(refs, None)
    assert not stale.exists(), "잔여 임시 사본이 정리되지 않았다"
