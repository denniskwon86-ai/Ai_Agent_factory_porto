"""선반의 키트를 **플랫폼이 읽는가** — 등록 경로 잇기.

이 시험이 지키는 것: 생성기가 낸 키트는 `starter_kits/` 에 쌓이는데, 등록부는
`docs/data-kits/*.kit.json` 만 훑었다. 변환기(`profile_from_manifest`)는 있었지만
**`demo_vertical_slice` 하나만 불렀다** — 시연 수직 경로에만 쓰였고, 선반에 무엇을
올려도 **조직에 붙일 수 없었다**(`POST /instances` 는 등록부를 본다).
"""
import json
import os

import pytest

from core.data_preparation import kit_registry as kr
from core.data_preparation.store import DataPreparationStore


@pytest.fixture()
def store(tmp_path):
    return DataPreparationStore(str(tmp_path / "dp.db"))


def _kit(root, kit_id, version, manifest, frozen=True):
    d = os.path.join(root, kit_id, version)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    if frozen:
        open(os.path.join(d, ".frozen"), "w").close()
    return d


def _manifest(kit_id="KIT-T", version="1.0.0", **kw):
    m = {"kit_id": kit_id, "version": version, "data_class": "SYNTHETIC",
         "datasets": [{"dataset_id": "MDM-01", "name": "품목"}],
         "app_blueprints": [{"app_id": "APP-01", "name": "앱", "datasets": ["MDM-01"]}]}
    m.update(kw)
    return m


# ── 무엇을 올리고 무엇을 빼나

def test_봉인된_판본만_올린다(tmp_path, monkeypatch):
    """★ **작업 중인 판본을 조직에 붙이면, 그 뒤 내용이 바뀌어도 붙인 쪽은 모른다.**"""
    root = tmp_path / "kits"
    _kit(str(root), "KIT-A", "1.0.0", _manifest("KIT-A"), frozen=True)
    _kit(str(root), "KIT-B", "1.0.0", _manifest("KIT-B"), frozen=False)
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(root))
    assert [k.kit_id for k in kr.discover_starter_kits()] == ["KIT-A"]


def test_모르는_data_class_는_올리지_않는다(tmp_path, monkeypatch):
    """지어내지 않는다 — `mode` 는 `DEMO/SYNTHETIC` 과 `REAL` 뿐이다."""
    root = tmp_path / "kits"
    _kit(str(root), "KIT-A", "1.0.0", _manifest("KIT-A", data_class="뭔가다른것"))
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(root))
    assert kr.discover_starter_kits() == []


def test_깨진_manifest_는_건너뛰고_나머지를_올린다(tmp_path, monkeypatch):
    """★ 선반에는 **구조가 다른 옛 키트**도 있다. 그것 때문에 등록 전체가 멈추면
    쓸 수 있는 키트까지 못 쓴다. (`discover()` 는 반대로 던진다 — 거기 있는 파일은
    전부 등록 대상이기 때문이다.)"""
    root = tmp_path / "kits"
    d = _kit(str(root), "KIT-BAD", "1.0.0", _manifest("KIT-BAD"))
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        f.write("{깨진")
    _kit(str(root), "KIT-OK", "1.0.0", _manifest("KIT-OK"))
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(root))
    assert [k.kit_id for k in kr.discover_starter_kits()] == ["KIT-OK"]


def test_이름은_kit_name_회사명_식별자_순으로_떨어진다(tmp_path, monkeypatch):
    """⚠️ 옛 판본에는 `kit_name` 이 없어 **회사 이름이 카탈로그에 뜬다**(D4)."""
    root = tmp_path / "kits"
    _kit(str(root), "KIT-N", "1.0.0", _manifest("KIT-N", kit_name="제 이름", company_name="회사"))
    _kit(str(root), "KIT-C", "1.0.0", _manifest("KIT-C", company_name="회사만"))
    _kit(str(root), "KIT-X", "1.0.0", _manifest("KIT-X"))
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(root))
    got = {k.kit_id: k.name for k in kr.discover_starter_kits()}
    assert got == {"KIT-N": "제 이름", "KIT-C": "회사만", "KIT-X": "KIT-X"}


def test_계약키를_옮겨_담는다(tmp_path, monkeypatch):
    """raw 로 넣으면 준비도 보드가 계약키를 0 개로 본다(2026-08-23 실측)."""
    root = tmp_path / "kits"
    _kit(str(root), "KIT-A", "1.0.0", _manifest("KIT-A"))
    monkeypatch.setenv(kr.STARTER_KITS_DIR_ENV, str(root))
    p = kr.discover_starter_kits()[0].profile
    assert kr.dataset_keys(p) == ["MDM-01"]
    assert [o["output"] for o in kr.outputs(p)] == ["APP-01"]
    assert p["kit_source"] == "STARTER_KIT"        # Profile 과 갈라 보이게


# ── 실제 선반

def test_실제_선반의_봉인_판본이_전부_잡힌다():
    ids = {(k.kit_id, k.version) for k in kr.discover_starter_kits()}
    assert ("KIT-MFG-SMELTING-NONFERROUS", "1.2.0") in ids
    assert ("KIT-MFG-BATTERY-MATERIALS", "1.2.0") in ids
    assert ("KIT-MFG-NONFERROUS-PROCUREMENT", "1.2.0") in ids


def test_시연_경로와_지문이_같다():
    """★★★ **둘이 다르면 등록부가 거부한다**(P3-2 — 동결 판본의 지문이 달라졌다).

    `demo_vertical_slice.register_kit()` 은 manifest 원문으로 지문을 낸다. 여기서
    대장(`fingerprint.json`)을 쓰면 더 정확해 보이지만, **먼저 부른 쪽이 이기는
    싸움**이 된다.
    """
    from core import demo_vertical_slice as dv
    mine = [k for k in kr.discover_starter_kits()
            if k.kit_id == dv.KIT_ID and k.version == dv.KIT_VERSION][0]
    assert mine.fingerprint == kr.file_fingerprint(os.path.join(dv.kit_root(), "manifest.json"))


# ── 등록 — 조직에 붙일 수 있는가

def test_두_곳을_함께_등록한다(store):
    """`docs/data-kits/*.kit.json`(운영 템플릿)과 `starter_kits/`(샘플 패키지)."""
    rows = kr.register_all(store)
    assert len(rows) >= 2
    got = {(r["kit_id"], r["version"]) for r in rows}
    assert ("afs_materials_procurement_v1", "1.0.0") in got          # Profile
    assert ("KIT-MFG-SMELTING-NONFERROUS", "1.2.0") in got           # 선반


def test_등록하면_인스턴스를_만들_수_있다(store):
    """★ **이것이 등록의 목적이다.** `POST /instances` 는 `resolve()` 로 판본을 찾고,
    없으면 404 다 — 선반에 있어도 등록되지 않으면 조직에 붙일 수 없다."""
    kr.register_all(store)
    row = kr.resolve(store, "KIT-MFG-SMELTING-NONFERROUS", "1.2.0")
    assert row and row.get("fingerprint")
    assert kr.dataset_keys(row["profile"]), "계약키가 비어 있으면 준비도가 0 으로 보인다"


def test_다시_등록해도_거부되지_않는다(store):
    """멱등해야 한다 — `GET /kits` 가 호출될 때마다 부른다."""
    a = kr.register_all(store)
    b = kr.register_all(store)
    assert len(a) == len(b)


def test_시연_등록과_섞여도_거부되지_않는다(store):
    """★ 같은 판본을 두 경로가 등록한다. 지문이 다르면 **P3-2 가 거부**한다."""
    from core import demo_vertical_slice as dv
    kr.register_all(store)
    dv.register_kit(store)                 # 시연 경로 — 같은 1.0.0
    kr.register_all(store)                 # 다시 — 여기서 거부되면 안 된다
    assert kr.resolve(store, dv.KIT_ID, dv.KIT_VERSION)
