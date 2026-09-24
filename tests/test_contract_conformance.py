"""인증 전 계약 대조(`core/data_preparation/contract_conformance.py`). 격리 runner 전용.

계약과 표는 **키트 정본**(`starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0`)에서 읽는다 —
손으로 적은 계약은 그 fixture 가 계약을 대신 정의한다. 원문 시험만 tmp 에 쓴다.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from core.data_preparation import contract_conformance as cc

KIT = Path(__file__).resolve().parents[1] / "starter_kits" / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.0.0"


def contract(key):
    return json.loads((KIT / "contracts" / f"{key}.contract.json").read_text(encoding="utf-8-sig"))


def sample(key, n=4):
    with (KIT / "samples" / "quick" / f"{key}.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames), [dict(r) for _, r in zip(range(n), reader)]


def codes(issues):
    return [i["code"] for i in issues]


@pytest.mark.parametrize("key", ["INV-01", "INV-02", "MDM-05", "MDM-06", "MFG-01", "MFG-02", "MFG-03", "QLT-01"])
def test_canonical_samples_conform_to_their_contract(key):
    columns, rows = sample(key)
    assert cc.inspect(contract(key), columns, rows) == []


def test_the_single_column_snapshot_that_reached_production_is_refused():
    """★★★ 실측된 결함 그대로 — `amount` 한 칸짜리 INV-01 판."""
    issues = cc.inspect(contract("INV-01"), ["amount"], [{"amount": "1"}])
    required, keys = cc.requirements(contract("INV-01"))
    assert issues == [{"code": cc.MISSING_FIELD, "fields": required}]
    assert set(keys) <= set(issues[0]["fields"])


def test_a_missing_required_column_is_named_and_row_checks_are_skipped():
    columns, rows = sample("INV-01")
    columns = [c for c in columns if c != "as_of_date"]
    assert cc.inspect(contract("INV-01"), columns, rows) == [{"code": cc.MISSING_FIELD, "fields": ["as_of_date"]}]


def test_a_missing_business_key_column_is_a_missing_field():
    columns, rows = sample("INV-01")
    issues = cc.inspect(contract("INV-01"), [c for c in columns if c != "snapshot_id"], rows)
    assert issues == [{"code": cc.MISSING_FIELD, "fields": ["snapshot_id"]}]


@pytest.mark.parametrize("blank", ["", "   "])
def test_an_empty_business_key_is_refused_by_line(blank):
    columns, rows = sample("INV-01")
    rows[1]["snapshot_id"] = blank
    assert cc.inspect(contract("INV-01"), columns, rows) == [
        {"code": cc.EMPTY_BUSINESS_KEY, "line": 3, "fields": ["snapshot_id"]}]


def test_a_duplicate_business_key_points_to_the_first_row():
    columns, rows = sample("INV-01")
    rows[3]["snapshot_id"] = rows[0]["snapshot_id"]
    assert cc.inspect(contract("INV-01"), columns, rows) == [
        {"code": cc.DUPLICATE_BUSINESS_KEY, "line": 5, "first_line": 2, "fields": ["snapshot_id"]}]


def test_whitespace_does_not_make_two_keys_different():
    columns, rows = sample("INV-01")
    rows[1]["snapshot_id"] = " " + rows[0]["snapshot_id"] + " "
    assert codes(cc.inspect(contract("INV-01"), columns, rows)) == [cc.DUPLICATE_BUSINESS_KEY]


def test_a_composite_key_is_compared_as_a_whole():
    """MDM-05 의 업무키는 (bom_id, line_no) 다 — 한 칸만 같으면 중복이 아니다."""
    columns, rows = sample("MDM-05")
    assert contract("MDM-05")["business_keys"] == ["bom_id", "line_no"]
    same_bom = [r for r in rows if r["bom_id"] == rows[0]["bom_id"]]
    assert len(same_bom) >= 2 and cc.inspect(contract("MDM-05"), columns, rows) == []
    rows[1] = {**rows[1], "bom_id": rows[0]["bom_id"], "line_no": rows[0]["line_no"]}
    assert codes(cc.inspect(contract("MDM-05"), columns, rows)) == [cc.DUPLICATE_BUSINESS_KEY]
    rows[2] = {**rows[2], "line_no": ""}
    assert codes(cc.inspect(contract("MDM-05"), columns, rows)) == [cc.DUPLICATE_BUSINESS_KEY, cc.EMPTY_BUSINESS_KEY]


def test_issues_carry_no_data_values():
    columns, rows = sample("INV-01")
    key = rows[0]["snapshot_id"]
    rows[1]["snapshot_id"] = key
    assert key not in repr(cc.inspect(contract("INV-01"), columns, rows))


@pytest.mark.parametrize("damage", ["no_schema", "no_keys", "key_not_a_field", "duplicate_field", "not_a_dict"])
def test_an_unreadable_contract_is_refused_not_skipped(damage):
    c = contract("INV-01")
    if damage == "no_schema":
        c.pop("schema")
    elif damage == "no_keys":
        c["business_keys"] = []
    elif damage == "key_not_a_field":
        c["business_keys"] = ["not_a_field"]
    elif damage == "duplicate_field":
        c["schema"]["fields"].append(dict(c["schema"]["fields"][0]))
    else:
        c = ["INV-01"]
    columns, rows = sample("INV-01")
    with pytest.raises(cc.ContractShapeError):
        cc.inspect(c, columns, rows)


def _raw(tmp_path, payload: bytes):
    path = tmp_path / "ds_test__INV-01.csv"
    path.write_bytes(payload)
    return {"raw_path": str(path), "checksum": hashlib.sha256(payload).hexdigest()}


def test_the_sealed_table_is_read_from_the_verified_raw(tmp_path):
    columns, rows = sample("INV-01", n=2)
    text = ",".join(columns) + "\n" + "".join(",".join(r[c] for c in columns) + "\n" for r in rows)
    got_columns, got_rows = cc.sealed_table(_raw(tmp_path, text.encode("utf-8")))
    assert got_columns == columns and got_rows == rows


def test_a_changed_raw_is_not_inspected(tmp_path):
    from core.data_preparation.certification_authority import CertificationError
    snapshot = _raw(tmp_path, b"snapshot_id\nA\n")
    Path(snapshot["raw_path"]).write_bytes(b"snapshot_id\nB\n")
    with pytest.raises(CertificationError) as caught:
        cc.sealed_table(snapshot)
    assert caught.value.reason_code == "RAW_CHECKSUM_MISMATCH"


@pytest.mark.parametrize("damage", ["no_path", "no_checksum", "gone"])
def test_a_missing_raw_blocks_instead_of_passing(tmp_path, damage):
    from core.data_preparation.certification_authority import CertificationError
    snapshot = _raw(tmp_path, b"snapshot_id\nA\n")
    if damage == "no_path":
        snapshot["raw_path"] = ""
    elif damage == "no_checksum":
        snapshot["checksum"] = ""
    else:
        Path(snapshot["raw_path"]).unlink()
    with pytest.raises(CertificationError) as caught:
        cc.sealed_table(snapshot)
    assert caught.value.reason_code == "RAW_UNAVAILABLE"
