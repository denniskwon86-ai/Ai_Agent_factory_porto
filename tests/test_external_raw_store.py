"""[DAO-1] 원문 보관소 — 계보의 마지막 고리와 **비밀값 차단기**.

이 파일이 지키는 것 셋.

1. 원문이 **지워지거나 조용히 바뀌지 않는다**(내용 주소 + `verify`).
2. 같은 응답을 다시 받아도 **중복 적재가 되지 않는다**.
3. ★★★ 비밀키가 **어떤 표기로도** 디스크에 닿지 않는다 — 그리고 그 검사기가 실제로 도달
   가능한지까지 본다(고지문이 아니라 차단기인지).
"""
import json
import os

import pytest

from core.external_intelligence.raw_store import (RawStore, RawStoreError, SecretLeakError,
                                                  assert_no_secret, redact, redact_url)

KEY = "abcdef0123456789abcdef0123456789"
SLASH_KEY = "abc/def0123456789xyzqrs"


@pytest.fixture()
def store(tmp_path):
    return RawStore(str(tmp_path / "external_raw"))


# ── 보존과 계보 ──────────────────────────────────────────────────────────────
def test_stores_payload_and_returns_checksum_ref(store):
    out = store.put(b'{"a":1}', source_id="SRC_DART", content_type="application/json")
    assert out["algorithm"] == "sha256"
    assert out["raw_object_ref"].startswith("SRC_DART/")
    assert out["raw_object_ref"].endswith(".json")
    assert store.read(out["raw_object_ref"]) == b'{"a":1}'


def test_metadata_sidecar_is_written(store):
    out = store.put(b"x" * 10, source_id="SRC_ECOS", job_id="job-1",
                    content_type="text/csv", note="1회차")
    meta = store.meta(out["raw_object_ref"])
    assert meta["job_id"] == "job-1"
    assert meta["byte_size"] == 10
    assert meta["source_id"] == "SRC_ECOS"
    assert meta["fetched_at"] and meta["stored_at"]


def test_verify_catches_silent_tampering(store):
    out = store.put(b"original", source_id="SRC_X", content_type="text/plain")
    assert store.verify(out["raw_object_ref"])["ok"] is True
    with open(os.path.join(store.root, out["raw_object_ref"]), "wb") as f:
        f.write(b"tampered")
    result = store.verify(out["raw_object_ref"])
    assert result["ok"] is False
    assert result["reason"] == "CHECKSUM_MISMATCH"


def test_verify_reports_missing_rather_than_raising(store):
    """★ 없는 것과 어긋난 것은 다른 상태다 — 둘을 접으면 사람이 할 일이 정해지지 않는다."""
    result = store.verify("SRC_X/ab/" + "0" * 64 + ".bin")
    assert result["ok"] is False
    assert result["reason"] == "MISSING"


# ── 재수집 방지 ──────────────────────────────────────────────────────────────
def test_same_payload_is_not_stored_twice(store):
    a = store.put(b"same", source_id="SRC_A", content_type="text/plain", job_id="j1")
    b = store.put(b"same", source_id="SRC_A", content_type="text/plain", job_id="j2")
    assert a["duplicate"] is False and b["duplicate"] is True
    assert a["raw_object_ref"] == b["raw_object_ref"]
    assert b["seen_count"] == 2
    #: ★ 최초 수집 시각은 **덮이지 않는다** — 계보가 「언제 처음 받았나」를 답해야 한다.
    assert b["fetched_at"] == a["fetched_at"]
    assert b["job_id"] == "j1"


def test_changed_payload_becomes_a_new_object(store):
    """원천이 값을 정정 공표하면 내용이 달라지므로 **옛 판이 남는다**."""
    a = store.put(b'{"v":1}', source_id="SRC_A", content_type="application/json")
    b = store.put(b'{"v":2}', source_id="SRC_A", content_type="application/json")
    assert a["raw_object_ref"] != b["raw_object_ref"]
    assert store.read(a["raw_object_ref"]) == b'{"v":1}'


def test_find_by_checksum_answers_already_collected(store):
    out = store.put(b"payload", source_id="SRC_A", content_type="text/plain")
    assert store.find_by_checksum("SRC_A", out["checksum"]) == out["raw_object_ref"]
    assert store.find_by_checksum("SRC_B", out["checksum"]) is None


def test_find_by_checksum_rejects_non_sha256(store):
    with pytest.raises(RawStoreError):
        store.find_by_checksum("SRC_A", "not-a-checksum")


def test_empty_payload_is_refused(store):
    """「자료 없음」을 **빈 파일로** 기록하면 0건이 적재 완료로 보인다 — 상태로 남겨야 한다."""
    with pytest.raises(RawStoreError):
        store.put(b"", source_id="SRC_A")


# ── 비밀값 차단기 ────────────────────────────────────────────────────────────
def test_redacts_key_in_query_string():
    out = redact_url("https://opendart.fss.or.kr/api/x.json?crtfc_key=" + KEY + "&corp_code=1", [KEY])
    assert KEY not in out
    assert "corp_code=1" in out


def test_redacts_key_in_path_segment():
    """★★★ ECOS 는 키를 **경로**에 둔다. 질의 문자열만 보는 검사기는 이것을 통과시킨다."""
    url = "https://ecos.bok.or.kr/api/StatisticSearch/" + KEY + "/json/kr/1/10/731Y001"
    out = redact_url(url, [KEY])
    assert KEY not in out
    assert "731Y001" in out


def test_redacts_by_param_name_without_a_secret_list():
    """호출부가 비밀 목록을 안 넘겼을 때의 두 번째 그물."""
    out = redact_url("https://x.test/a?serviceKey=" + KEY + "&b=1")
    assert KEY not in out
    assert "b=1" in out


def test_redacts_percent_encoded_secret_in_unknown_param():
    """⚠️⚠️ 실측으로 뚫렸던 자리. 인코딩된 채 목록 밖 이름에 들어오면 둘 다 놓쳤다."""
    url = "https://x.test/api?tok3n=abc%2Fdef0123456789xyzqrs&b=1"
    out = redact_url(url, [SLASH_KEY])
    from urllib.parse import unquote
    assert SLASH_KEY not in unquote(out)


def test_blocker_is_reachable_not_decoration():
    """★★★ 「검사기가 있다」가 아니라 「검사기가 실제로 잡는다」를 본다.

    삭제를 우회한 문자열을 **직접** 먹여 본다. 이것이 통과하면 차단기는 장식이다."""
    with pytest.raises(SecretLeakError):
        assert_no_secret("https://x/?a=abc%2Fdef0123456789xyzqrs", [SLASH_KEY], where="시험")
    with pytest.raises(SecretLeakError):
        assert_no_secret("key=" + KEY, [KEY], where="시험")


def test_put_refuses_to_write_when_a_secret_would_land_on_disk(store, monkeypatch):
    """삭제가 실패해도 **파일이 만들어지지 않는다.**

    ⚠️ 삭제기를 무력화해 차단기만 남긴다 — 두 층이 다 있어야 층이다."""
    monkeypatch.setattr("core.external_intelligence.raw_store.redact_url",
                        lambda url, secrets=None: str(url or ""))
    with pytest.raises(SecretLeakError):
        store.put(b"body", source_id="SRC_A", requested_url="https://x/?k=" + KEY, secrets=[KEY])
    assert not os.path.isdir(os.path.join(store.root, "SRC_A"))


def test_note_is_redacted_too(store):
    """오류 메시지가 키를 담아 비고로 흘러드는 경로."""
    out = store.put(b"body", source_id="SRC_A", note="호출 실패: key=" + KEY, secrets=[KEY])
    assert KEY not in out["note"]
    assert KEY not in json.dumps(store.meta(out["raw_object_ref"]), ensure_ascii=False)


def test_short_values_are_not_treated_as_secrets():
    """짧은 값을 지우면 URL 이 알아볼 수 없게 된다 — 「json」 같은 조각이 사라진다."""
    assert redact("a/json/b", ["json"]) == "a/json/b"


# ── 경로 안전 ────────────────────────────────────────────────────────────────
def test_reference_cannot_escape_the_store(store):
    """참조는 DB 를 거쳐 오므로 신뢰하지 않는다."""
    with pytest.raises(RawStoreError):
        store.read("../../../etc/passwd")
    assert store.exists("../../../etc/passwd") is False


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a\\b", "a b"])
def test_source_id_must_be_a_safe_segment(store, bad):
    with pytest.raises(RawStoreError):
        store.put(b"x", source_id=bad)


def test_default_root_is_the_gitignored_runtime_folder():
    """★ 원문은 저장소에 커밋되지 않는 자리에만 쌓인다(`.gitignore: data/external_raw/`)."""
    from core.paths import data_path
    assert RawStore().root == data_path("external_raw")
