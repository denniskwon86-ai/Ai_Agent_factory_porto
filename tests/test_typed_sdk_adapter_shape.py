"""★★★ 어댑터가 약속하는 모양과 브리지가 **실제로 돌려주는** 모양이 같아야 한다. (2026-08-28)

## ⚠️⚠️ 무엇이 있었나

생성된 앱이 화면에서 죽었다:

    Uncaught TypeError: Cannot read properties of undefined (reading 'forEach')

데이터는 **200 으로 잘 왔다**(`POST /appdata/runtime/proof` 200 ·
`GET /appdata/runtime/datasets/customers/records` 200). 그런데 이름이 달랐다:

    브리지가 돌려주는 것   { records, total, cursor }   hostRuntimeBridge.ts `data.list`
    어댑터가 약속한 것     { items, cursor? }           typed_sdk_adapter.py

앱은 어댑터의 타입을 믿고 `data.items` 를 읽었고, 그것은 `undefined` 였다.

★ **같은 계약을 두 곳이 각자 선언했고, 정본은 어디에도 없었다.** 이 저장소가 오늘만
  여섯 번 만난 모양이다 — 쓰는 곳과 찾는 곳의 출처가 다르면 둘 다 «맞는 값» 을 쓰면서
  서로를 못 찾는다.

## 왜 브리지에 맞췄나

브리지는 **실제로 도는 코드**다. 어댑터는 그것을 설명하는 타입일 뿐이다. 설명이 실물과
다르면 고칠 것은 설명이다.

## 이 시험이 하는 일

정본을 한 곳에 두지 못하는 대신(한쪽은 파이썬, 한쪽은 타입스크립트) **대조를 강제**한다.
어느 한쪽을 고치면 이 시험이 울고, 그때 사람이 둘을 맞춘다.
"""
import re
from pathlib import Path

import pytest

from core.typed_sdk_adapter import generate

_BRIDGE = Path("frontend/src/lib/hostRuntimeBridge.ts")


def _bridge_list_keys() -> set:
    """브리지의 `data.list` 가 돌려주는 객체의 **키 이름**."""
    src = _BRIDGE.read_text(encoding="utf-8", errors="replace")
    i = src.index("if (op === 'data.list')")
    #: 그 분기 안의 `const data = { ... }` 리터럴을 읽는다
    j = src.index("const data = {", i)
    k = src.index("};", j)
    body = src[j:k]
    #: ⚠️ ES6 **단축 속성**도 키다 — 브리지는 `total,` 로 쓴다(콜론 없음).
    #:   콜론만 찾으면 `total` 을 놓치고, 그러면 이 시험이 「브리지가 안 준다」고
    #:   거짓 실패한다(실제로 한 번 그랬다).
    keys = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", body, re.M))
    keys |= set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*$", body, re.M))
    return keys


def _adapter_list_keys(source: str) -> set:
    """생성된 어댑터의 `list` 반환 타입에 적힌 키 이름."""
    i = source.index("list: (page?")
    j = source.index("as Promise<", i)
    k = source.index(">,", j)
    return set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\??\s*:", source[j:k]))


#: ⚠️⚠️ 계약을 **내 말로 짓지 않는다.** 처음에 지어낸 fixture 는 `generate()` 가
#:   거절했고(필수 칸 누락), 그러면 이 시험은 「내 fixture 가 통과하는가」만 본다.
#:   실제로 승인된 계약을 쓴다 — 없으면 건너뛴다(있는 척하지 않는다).
_REAL_CONTRACT = Path("projects/CRM003/contracts/app_runtime_contract.json")


def _load_contract():
    import json
    return json.loads(_REAL_CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture()
def _adapter_source():
    if not _REAL_CONTRACT.exists():
        pytest.skip("승인된 계약 표본이 없다")
    out = generate(_load_contract())
    assert out.ok, getattr(out, "reason", out)
    return out.source


# ── 대조 ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _BRIDGE.exists(), reason="브리지 파일이 없다")
def test_어댑터와_브리지가_같은_이름을_쓴다(_adapter_source):
    """★★★ **이 파일의 요지.** 둘이 어긋나면 생성된 앱이 화면에서 죽는다."""
    bridge = _bridge_list_keys()
    adapter = _adapter_list_keys(_adapter_source)
    assert "records" in bridge, f"브리지가 records 를 안 돌려준다: {bridge}"
    missing = {k for k in adapter if k not in bridge}
    assert not missing, (
        f"어댑터가 약속한 키를 브리지가 안 돌려준다: {sorted(missing)}\\n"
        f"  브리지: {sorted(bridge)}\\n  어댑터: {sorted(adapter)}\\n"
        f"→ 실제로 도는 쪽(브리지)이 진실이다. 어댑터를 그쪽에 맞추십시오.")


def test_어댑터가_items_를_약속하지_않는다(_adapter_source):
    """★★★ 대조군 — 「고쳤다」가 아니라 **무엇을 고쳤는지**를 고정한다.

    ⚠️ 이 시험이 없으면 누가 `items` 로 되돌려도 아무도 모른다."""
    assert "items:" not in _adapter_source, (
        "어댑터가 다시 items 를 약속한다 — 브리지는 records 를 돌려준다")


def test_목록_타입에_records_와_total_이_있다(_adapter_source):
    keys = _adapter_list_keys(_adapter_source)
    assert "records" in keys and "total" in keys, keys


def test_읽기_권한이_없으면_list_를_만들지_않는다():
    """★ 대조군 — 위 시험들이 「항상 list 가 있다」에 기대지 않는지 본다.

    ⚠️ 계약을 지어내지 않고 **실제 계약에서 읽기 권한만 빼서** 만든다."""
    if not _REAL_CONTRACT.exists():
        pytest.skip("승인된 계약 표본이 없다")
    c = _load_contract()
    for ds in c.get("datasets", []):
        ds["allowed_actions"] = [a for a in (ds.get("allowed_actions") or [])
                                 if a not in ("read", "list")]
    out = generate(c)
    if not out.ok:
        pytest.skip(f"읽기 없는 계약은 정본 검증이 거절한다: {out.reason}")
    assert "list: (page?" not in out.source
