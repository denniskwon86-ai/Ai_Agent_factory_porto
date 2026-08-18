"""[BDR-202] Kit Registry — `docs/data-kits` 의 키트 문서를 읽어 판본으로 등록한다.

## 템플릿은 운영 Data Contract 가 아니다

★★★ 키트는 **「이런 표가 필요하다」는 제안**이지 「이 표가 있다」는 선언이 아니다.
  둘을 섞으면 키트를 등록하는 것만으로 데이터가 있는 것처럼 보이고, 그 위에서 계산이
  돌아 **없는 숫자로 경영 판단**을 하게 된다.

⚠️ 그래서 등록은 `kit_registry_versions` 에만 남고, 실제 데이터는 Kit Instance 에
  Source Binding 이 붙어 ACTIVE 가 됐을 때 비로소 생긴다.

## 깨진 키트·모르는 버전은 막는다

⚠️ 「일단 읽고 되는 만큼 쓰자」로 두면 필드 절반이 빠진 키트가 등록되고, 그것을 적용한
  조직은 «왜 이 항목이 없지» 를 나중에 발견한다 — 그때는 이미 데이터를 넣은 뒤다.
"""
import hashlib
import os
import re
from typing import Any, Dict, List, NamedTuple, Optional

from core.data_preparation import models as m

#: 키트 문서가 있는 곳(저장소 기준 절대경로).
KITS_DIRNAME = os.path.join("docs", "data-kits")

#: 기계 Profile 파일 이름. 문서 옆에 두고, **없으면 등록하지 않는다.**
#: ⚠️ 사람이 읽는 문서만으로 등록하면 필드 목록을 사람이 옮겨 적게 되고, 옮겨 적는
#:   순간 두 정본이 생긴다.
PROFILE_SUFFIX = ".kit.json"

#: 시연 등록 키트.
DEMO_KIT_ID = "afs_materials_procurement_v1"
DEMO_KIT_NAME = "원료 구매·도입 경영 키트"

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class KitLoadError(m.DataPreparationError):
    """키트를 읽을 수 없다 — 등록하지 않는다."""


class LoadedKit(NamedTuple):
    kit_id: str
    version: str
    name: str
    mode: str
    source_path: str
    fingerprint: str
    profile: Dict[str, Any]


def kits_dir() -> str:
    from core.paths import PROJECT_ROOT
    return os.path.join(PROJECT_ROOT, KITS_DIRNAME)


def file_fingerprint(path: str) -> str:
    """키트 **원문**의 지문. 문서가 한 글자라도 바뀌면 달라진다.

    ★ 내용에서 유도한다 — 파일 시각이나 경로를 쓰면 같은 문서가 옮겨 다닐 때마다
      다른 키트로 보인다."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require(profile: Dict[str, Any], key: str, path: str) -> Any:
    if key not in profile:
        raise KitLoadError(f"{os.path.basename(path)}: 필수 항목 «{key}» 가 없습니다 — "
                           f"반쪽 키트를 등록하면 적용한 조직이 나중에 발견합니다.")
    return profile[key]


def load_profile(path: str) -> LoadedKit:
    """기계 Profile 하나를 읽는다. **깨졌으면 던진다** — 되는 만큼 쓰지 않는다."""
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    except Exception as e:
        raise KitLoadError(f"{os.path.basename(path)}: 판독 실패 — {str(e)[:120]}")
    if not isinstance(profile, dict):
        raise KitLoadError(f"{os.path.basename(path)}: 최상위가 객체가 아닙니다.")

    kit_id = str(_require(profile, "kit_id", path) or "").strip()
    version = str(_require(profile, "version", path) or "").strip()
    name = str(_require(profile, "name", path) or "").strip()
    mode = str(profile.get("mode", m.KIT_MODE_DEMO) or "").strip()

    if not kit_id:
        raise KitLoadError(f"{os.path.basename(path)}: kit_id 가 비어 있습니다.")
    if not _VERSION.match(version):
        #: ⚠️ 「모르는 버전」을 받아 주면 정렬도 비교도 못 하게 되고, 그때 «최신» 이
        #:   무엇인지 아무도 답할 수 없다.
        raise KitLoadError(
            f"{os.path.basename(path)}: version 은 `X.Y.Z` 여야 합니다(현재 {version!r}).")
    if mode not in m.KIT_MODES:
        raise KitLoadError(
            f"{os.path.basename(path)}: mode 는 {list(m.KIT_MODES)} 중 하나여야 합니다.")

    datasets = profile.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise KitLoadError(
            f"{os.path.basename(path)}: datasets 가 비어 있습니다 — 표가 없는 키트는 "
            f"적용해도 아무 일이 일어나지 않습니다.")
    for ds in datasets:
        if not isinstance(ds, dict) or not str(ds.get("dataset_contract_key", "")).strip():
            raise KitLoadError(
                f"{os.path.basename(path)}: 모든 데이터셋에 `dataset_contract_key` 가 "
                f"있어야 합니다 — 그것이 결속이 가리키는 이름입니다.")

    return LoadedKit(kit_id=kit_id, version=version, name=name, mode=mode,
                     source_path=os.path.basename(path),
                     fingerprint=file_fingerprint(path), profile=profile)


def discover(directory: str = "") -> List[LoadedKit]:
    """키트 디렉터리를 훑는다. **깨진 파일은 던진다** — 조용히 건너뛰지 않는다.

    ⚠️ 건너뛰면 「키트가 없다」와 「키트가 깨졌다」가 같은 모양이 되고, 등록 화면은
      아무것도 없는 것처럼 보인다."""
    root = directory or kits_dir()
    if not os.path.isdir(root):
        return []
    out: List[LoadedKit] = []
    for name in sorted(os.listdir(root)):
        if name.endswith(PROFILE_SUFFIX):
            out.append(load_profile(os.path.join(root, name)))
    return out


def register_all(store: Any, directory: str = "") -> List[Dict[str, Any]]:
    """찾은 키트를 전부 등록한다(멱등). 반환은 등록된 판본들."""
    rows = []
    for kit in discover(directory):
        rows.append(store.upsert_kit_version(
            kit_id=kit.kit_id, version=kit.version, name=kit.name, mode=kit.mode,
            source_path=kit.source_path, fingerprint_value=kit.fingerprint,
            profile=kit.profile))
    return rows


def dataset_keys(profile: Any) -> List[str]:
    """이 키트가 요구하는 데이터셋 계약 이름들. **정렬해 돌려준다.**"""
    if not isinstance(profile, dict):
        return []
    return sorted({str(d.get("dataset_contract_key", "")).strip()
                   for d in (profile.get("datasets") or [])
                   if isinstance(d, dict) and str(d.get("dataset_contract_key", "")).strip()})


def resolve(store: Any, kit_id: str, version: str) -> Optional[Dict[str, Any]]:
    """등록된 판본을 찾는다. **모르는 버전은 `None`** — 추측해 최신을 주지 않는다.

    ⚠️ 「없으면 최신으로」는 편해 보이지만, 사용자가 고른 것과 적용된 것이 달라지고
      그 차이는 데이터가 들어간 뒤에야 드러난다."""
    return store.get_kit_version(kit_id, version)
