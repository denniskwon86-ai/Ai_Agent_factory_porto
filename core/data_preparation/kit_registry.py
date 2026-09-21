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
STARTER_PACKAGES_DIRNAME = "starter_kits"

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
    #: 확정 판본인가 — Starter Package 의 `.frozen`·`manifest.status` 에서 읽는다.
    #: 등록부가 이 값으로 **지문이 달라지는 재등록을 거부한다** (P3-2).
    frozen: bool = False


#: ⚠️ **키트를 코드 배포에서 떼어내기 위한 자리다.**
#:
#:   `deploy/update.sh` 는 `/opt/afs/app` 을 `git pull` 로 갈아 끼우고 `/opt/afs/data`
#:   는 남긴다. 그런데 키트는 **app 쪽**에 있어 코드 릴리스에 묶여 있다 — 산업이 늘면
#:   **모든 고객 서버가 그 짐을 함께 받고**, 제련만 쓰는 곳도 전선·화학 키트를 받는다.
#:
#:   환경변수를 두면 지금은 아무것도 달라지지 않고(기본값이 같다), 나중에
#:   `/opt/afs/data/kits/` 로 옮기거나 배급 시스템을 붙일 때 **설정 한 줄**이면 된다.
KITS_DIR_ENV = "AFS_KITS_DIR"
STARTER_KITS_DIR_ENV = "AFS_STARTER_KITS_DIR"


def _dir_from_env(env_name: str, default_rel: str) -> str:
    """환경변수가 있으면 그곳, 없으면 저장소 안의 기본 자리.

    ⚠️ **상대 경로는 `PROJECT_ROOT` 기준으로 읽는다.** cwd 기준으로 두면 서비스로
      돌 때와 손으로 돌릴 때가 달라져, 「키트가 없다」가 조용히 나온다.
    """
    from core.paths import PROJECT_ROOT
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return os.path.join(PROJECT_ROOT, default_rel)
    return raw if os.path.isabs(raw) else os.path.join(PROJECT_ROOT, raw)


def kits_dir() -> str:
    """Profile(`*.kit.json`) 디렉터리. `AFS_KITS_DIR` 이 우선한다."""
    return _dir_from_env(KITS_DIR_ENV, KITS_DIRNAME)


def starter_packages_dir() -> str:
    """Starter Kit 디렉터리. `AFS_STARTER_KITS_DIR` 이 우선한다."""
    return _dir_from_env(STARTER_KITS_DIR_ENV, STARTER_PACKAGES_DIRNAME)


def _freeze_state(version_root: str) -> Dict[str, Any]:
    """판본 디렉터리의 동결·무결성 상태. 카탈로그 행에 그대로 얹는다."""
    from core.data_preparation import kit_freeze
    frozen = kit_freeze.is_frozen(version_root)
    has_ledger = kit_freeze.load_fingerprints(version_root) is not None
    ok, problems = kit_freeze.verify(version_root)
    return {
        "frozen": frozen,
        "fingerprint_ledger": has_ledger,
        #: 대장이 없으면 「검사하지 않았다」이지 「통과했다」가 아니다 — 셋을 구분한다.
        "integrity": "PASS" if (has_ledger and ok) else ("FAIL" if has_ledger else "UNVERIFIED"),
        "integrity_problems": problems[:10],
    }


def starter_package_catalog(directory: str = "") -> List[Dict[str, Any]]:
    """샘플 기업 Starter Package 카탈로그를 읽는다 — 운영 등록과 분리한다.

    `docs/data-kits` 의 Profile은 조직에 적용할 운영 템플릿이고, `starter_kits` 는
    샘플 기업·합성 데이터·앱·보고서를 묶은 체험 패키지다. 둘을 한 목록으로 그리면 옛
    9개 데이터셋 Profile이 두 번째 샘플 회사처럼 보인다. 준비 중 패키지는 등록하지 않되
    카탈로그에는 남겨 전체 모수와 상태를 숨기지 않는다.
    """
    import json
    from core.paths import PROJECT_ROOT

    root = directory or starter_packages_dir()
    if not os.path.isdir(root):
        return []
    out: List[Dict[str, Any]] = []
    for kit_id in sorted(os.listdir(root)):
        kit_root = os.path.join(root, kit_id)
        if not os.path.isdir(kit_root):
            continue
        for version in sorted(os.listdir(kit_root)):
            manifest_path = os.path.join(kit_root, version, "manifest.json")
            if not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception as e:
                raise KitLoadError(
                    f"{kit_id}/{version} 샘플 패키지 manifest 를 읽을 수 없습니다: "
                    f"{str(e)[:120]}")
            if not isinstance(manifest, dict):
                raise KitLoadError(f"{kit_id}/{version} manifest 최상위가 객체가 아닙니다.")
            manifest_id = str(manifest.get("kit_id") or "").strip()
            manifest_version = str(manifest.get("version") or "").strip()
            if manifest_id != kit_id or manifest_version != version:
                raise KitLoadError(
                    f"{kit_id}/{version} 경로와 manifest 정체성이 일치하지 않습니다.")
            raw_status = str(manifest.get("status") or "").strip()
            available = raw_status == "VALIDATED_FOR_DEMO"
            datasets = manifest.get("datasets")
            apps = manifest.get("app_blueprints")
            reports = manifest.get("report_templates") or manifest.get("reports")
            from core.data_preparation.business_kits import represented_business_kits
            dataset_keys = [str(d.get("dataset_contract_key") or d.get("dataset_id") or "")
                            for d in datasets if isinstance(d, dict)] \
                if isinstance(datasets, list) else []
            out.append({
                "kit_id": kit_id,
                "version": version,
                "name": str(manifest.get("company_name") or kit_id).strip(),
                "description": str(manifest.get("industry")
                                   or manifest.get("primary_use_case") or "").strip(),
                "data_kind": "DEMO/SYNTHETIC",
                "catalog_status": "AVAILABLE_FOR_DEMO" if available else "PREPARING",
                "selectable": available,
                "dataset_count": len(datasets) if isinstance(datasets, list)
                    else int(manifest.get("dataset_count") or 0),
                "app_count": len(apps) if isinstance(apps, list) else 0,
                "report_count": len(reports) if isinstance(reports, list) else 0,
                # 준비 중 패키지의 `dataset_count` 숫자만으로 업무기능이 구현됐다고 말하지
                # 않는다. 실제 데이터 계약 목록이 있는 판에서만 센다.
                "business_kit_count": len(represented_business_kits(dataset_keys)),
                # 판본이 확정(동결)됐는가와, 파일이 그 뒤로 바뀌지 않았는가 (P3-3).
                # ⚠️ 화면에 「확정」이라고만 쓰고 대조 결과를 숨기면, 파일이 바뀐 판본을
                #   확정된 것으로 보여 주게 된다 — 그것이 이 열들을 함께 내보내는 이유다.
                **_freeze_state(os.path.join(kit_root, version)),
            })
    # 지금 바로 쓸 수 있는 패키지를 먼저. 준비 중 자산이 첫 선택처럼 보이면 첫 클릭부터 막힌다.
    return sorted(out, key=lambda row: (not bool(row["selectable"]), row["name"]))


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

    #: ★★★ 산출물이 **없는 데이터셋을 요구하면** 키트를 등록하지 않는다.
    #: ⚠️ 「모르는 이름은 건너뛴다」로 두면 오타 하나가 요구사항을 지우고, 그 산출물은
    #:   준비도 판정에서 **늘 AVAILABLE** 이 된다 — 아무 데이터 없이도.
    keys = {str(ds.get("dataset_contract_key", "")).strip() for ds in datasets}
    for spec in (profile.get("outputs") or []):
        if not isinstance(spec, dict) or not str(spec.get("output", "")).strip():
            raise KitLoadError(
                f"{os.path.basename(path)}: 모든 산출물에 `output` 이름이 있어야 합니다.")
        needs = spec.get("requires")
        if not isinstance(needs, list) or not needs:
            raise KitLoadError(
                f"{os.path.basename(path)}: 산출물 «{spec.get('output')}» 이 요구하는 "
                f"데이터가 없습니다 — 아무것도 요구하지 않는 산출물은 데이터가 하나도 "
                f"없어도 «가능» 으로 보입니다.")
        unknown = sorted({str(k).strip() for k in needs} - keys)
        if unknown:
            raise KitLoadError(
                f"{os.path.basename(path)}: 산출물 «{spec.get('output')}» 이 이 키트에 "
                f"없는 데이터를 요구합니다: {unknown}")

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


#: `manifest.data_class` → 등록부의 `mode`. **지어내지 않는다** — 모르는 값은 거부한다
_DATA_CLASS_TO_MODE = {"SYNTHETIC": m.KIT_MODE_DEMO, "REAL": m.KIT_MODE_REAL}


def _starter_kit_profile(vdir: str) -> Optional[LoadedKit]:
    """선반의 판본 하나를 **등록 가능한 프로파일**로 읽는다. 아니면 `None`.

    ⚠️ **봉인된 것만 올린다.** 작업 중인 판본을 조직에 붙이면, 그 뒤 내용이 바뀌어도
      붙인 쪽은 모른다. 등록부가 「동결 판본의 지문이 달라지면 거부」(P3-2)로 지키는
      것도 **동결됐다고 적힌 판본**에 한해서다.
    """
    import json
    from core.data_preparation import kit_freeze

    if not kit_freeze.is_frozen(vdir):
        return None
    mpath = os.path.join(vdir, "manifest.json")
    if not os.path.isfile(mpath):
        return None
    try:
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
        profile = profile_from_manifest(manifest)
    except (OSError, ValueError, KitLoadError):
        #: ⚠️ **조용히 건너뛴다.** 선반에는 구조가 다른 옛 키트도 있고, 그것 때문에
        #:   등록 전체가 멈추면 쓸 수 있는 키트까지 못 쓴다. (`discover()` 는 반대로
        #:   던진다 — 거기 있는 파일은 전부 등록 대상이기 때문이다.)
        return None

    kit_id = str(manifest.get("kit_id") or "").strip()
    version = str(manifest.get("version") or "").strip()
    if not kit_id or not _VERSION.match(version):
        return None
    mode = _DATA_CLASS_TO_MODE.get(str(manifest.get("data_class") or "").strip().upper())
    if not mode:
        return None
    #: ★ 이름은 `kit_name` → `company_name` → `kit_id` 로 떨어진다. 옛 판본에는
    #:   `kit_name` 이 없어 **회사 이름이 카탈로그에 뜬다** — 그 사실을 감추지 않는다.
    name = (str(manifest.get("kit_name") or "").strip()
            or str(manifest.get("company_name") or "").strip() or kit_id)
    #: ⚠️ **지문은 manifest 원문에서 뽑는다 — 대장(`fingerprint.json`)이 아니다.**
    #:
    #:   대장이 내용 전체를 담아 더 정확해 보이지만, `demo_vertical_slice.register_kit()`
    #:   이 **같은 판본을 manifest 지문으로 이미 등록한다.** 둘이 다르면 등록부가
    #:   「동결 판본의 지문이 달라졌다」로 **거부**한다(P3-2) — 먼저 부른 쪽이 이기는
    #:   싸움이 된다. 내용이 조용히 바뀌는 것은 `kit_freeze.verify()` 가 대장으로 막고,
    #:   여기 지문은 **변경 감지**가 일이다.
    fp = file_fingerprint(mpath)
    profile["kit_source"] = "STARTER_KIT"        # Profile(`*.kit.json`) 과 갈라 보이게
    return LoadedKit(kit_id=kit_id, version=version, name=name, mode=mode,
                     source_path=mpath, fingerprint=fp, profile=profile, frozen=True)


def discover_starter_kits(directory: str = "") -> List[LoadedKit]:
    """선반(`starter_kits/<KIT_ID>/<판본>/`)에서 등록 가능한 것을 찾는다.

    ★ 이것이 **생성기가 낸 키트를 플랫폼이 읽는 자리**다. 예전에는
      `profile_from_manifest()` 를 `demo_vertical_slice` 만 불러, 시연 수직 경로
      하나에만 쓰였다 — 선반에 무엇을 올려도 조직에 붙일 수 없었다.
    """
    root = directory or starter_packages_dir()
    if not os.path.isdir(root):
        return []
    out: List[LoadedKit] = []
    for kit_id in sorted(os.listdir(root)):
        kdir = os.path.join(root, kit_id)
        if not os.path.isdir(kdir):
            continue
        for ver in sorted(n for n in os.listdir(kdir)
                          if os.path.isdir(os.path.join(kdir, n))):
            kit = _starter_kit_profile(os.path.join(kdir, ver))
            if kit is not None:
                out.append(kit)
    return out


def register_all(store: Any, directory: str = "",
                 starter_directory: str = "") -> List[Dict[str, Any]]:
    """찾은 키트를 전부 등록한다(멱등). 반환은 등록된 판본들.

    **두 곳에서 찾는다** — `docs/data-kits/*.kit.json`(운영 템플릿)과
    `starter_kits/`(샘플 기업 패키지). 둘은 성격이 다르므로 프로파일의
    `kit_source` 로 갈라 둔다.

    ⚠️ 자리를 둘 다 인자로 받는다. **Profile 만 인자를 받고 선반은 못 받으면**,
      임시 디렉터리로 격리하려는 쪽이 실제 선반까지 끌어온다.
    """
    rows = []
    for kit in list(discover(directory)) + list(discover_starter_kits(starter_directory)):
        rows.append(store.upsert_kit_version(
            kit_id=kit.kit_id, version=kit.version, name=kit.name, mode=kit.mode,
            source_path=kit.source_path, fingerprint_value=kit.fingerprint,
            profile=kit.profile, frozen=kit.frozen))
    return rows


def profile_from_manifest(manifest: Any) -> Dict[str, Any]:
    """정본 키트 `manifest.json` → **등록부가 읽는 프로파일**.

    ## ⚠️⚠️ 왜 필요한가 — 같은 것을 두 이름으로 부르고 있었다

    정본 manifest 는 데이터셋을 `dataset_id`·`name` 으로 적고, 이 모듈의 독자
    (`dataset_keys`·`dataset_labels`·`load_profile`)는 `dataset_contract_key`·`label`
    을 찾는다. 그래서 정본 키트를 **raw 로** 등록하면 준비도 보드가 계약키를 **0개**로
    보고, 인증판이 7종 있는데도 「required 0 / ready 0」 으로 답한다(2026-08-23 실측).

    ★ 0은 「없다」로 읽힌다. 화면은 아무 말도 못 하고, 사용자는 다음에 무엇을 할지
      알 수 없다.

    ## 무엇을 옮기는가

        dataset_contract_key ← dataset_id
        label                ← name
        outputs[]            ← app_blueprints[] (`app_id` 가 산출물, `datasets` 가 요구)

    ⚠️ `purpose` 는 manifest 에 없다 — **비워 둔다.** 계약 이름을 이름칸에 복사하면
      화면이 「이름이 없다」와 「이름이 계약과 같다」를 구분할 수 없다(`dataset_labels`
      머리말과 같은 규칙).
    ⚠️ 옮기지 못한 것을 지어내지 않는다. 산출물이 없는 manifest 는 산출물 없이 등록된다.
    """
    if not isinstance(manifest, dict):
        raise KitLoadError("manifest 의 최상위가 객체가 아닙니다.")
    src = manifest.get("datasets")
    if not isinstance(src, list) or not src:
        raise KitLoadError("manifest 에 datasets 가 없습니다.")

    datasets: List[Dict[str, Any]] = []
    for d in src:
        if not isinstance(d, dict):
            continue
        key = str(d.get("dataset_contract_key") or d.get("dataset_id") or "").strip()
        if not key:
            #: ⚠️ 이름 없는 데이터셋을 조용히 건너뛰지 않는다 — 건너뛰면 요구사항이
            #:   줄고, 그 산출물은 준비도에서 늘 «가능» 이 된다.
            raise KitLoadError(f"이름 없는 데이터셋이 있습니다: {d}")
        datasets.append({
            "dataset_contract_key": key,
            "label": str(d.get("label") or d.get("name") or "").strip(),
            "purpose": str(d.get("purpose") or "").strip(),
            "required": bool(d.get("required", True)),
            "keys": list(d.get("keys") or []),
            "deps": list(d.get("deps") or []),
        })

    known = {d["dataset_contract_key"] for d in datasets}
    outputs: List[Dict[str, Any]] = []
    for bp in (manifest.get("outputs") or manifest.get("app_blueprints") or []):
        if not isinstance(bp, dict):
            continue
        name = str(bp.get("output") or bp.get("app_id") or "").strip()
        needs = [str(x).strip() for x in (bp.get("requires") or bp.get("datasets") or [])
                 if str(x).strip()]
        if not name or not needs:
            #: ⚠️ 아무것도 요구하지 않는 산출물은 데이터가 하나도 없어도 «가능» 으로
            #:   보인다 — 그런 것은 등록하지 않는다.
            continue
        unknown = sorted(set(needs) - known)
        if unknown:
            raise KitLoadError(
                f"산출물 «{name}» 이 이 키트에 없는 데이터를 요구합니다: {unknown}")
        outputs.append({"output": name, "label": str(bp.get("name") or "").strip(),
                        "requires": sorted(set(needs))})

    #: ★ 원본을 **버리지 않는다.** 옮기지 못한 칸(회사 프로파일·파일 색인 등)이
    #:   나중에 필요할 수 있고, 그때 「원본이 어디 갔나」를 묻게 된다.
    out = dict(manifest)
    out["datasets"] = datasets
    out["outputs"] = outputs
    return out


def dataset_keys(profile: Any) -> List[str]:
    """이 키트가 요구하는 데이터셋 계약 이름들. **정렬해 돌려준다.**"""
    if not isinstance(profile, dict):
        return []
    return sorted({str(d.get("dataset_contract_key", "")).strip()
                   for d in (profile.get("datasets") or [])
                   if isinstance(d, dict) and str(d.get("dataset_contract_key", "")).strip()})


def dataset_labels(profile: Any) -> Dict[str, Dict[str, str]]:
    """계약 이름 → 사람이 읽는 이름·쓰임새.

    ★★★ 설계 §12: 기술 ID 를 앞세우지 않는다. 그런데 이름은 **계약과 함께** 산다 —
      화면마다 제 나름의 번역표를 두면 같은 데이터가 화면마다 다른 이름으로 불린다.
      그래서 여기서 한 번 꺼내 모든 응답에 실어 보낸다.

    ⚠️ 이름이 선언되지 않았으면 **비워 둔다**. 계약 이름을 그대로 이름칸에 복사하면
      화면은 「이름이 없다」와 「이름이 계약 이름과 같다」를 구분할 수 없다."""
    if not isinstance(profile, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for d in (profile.get("datasets") or []):
        if not isinstance(d, dict):
            continue
        key = str(d.get("dataset_contract_key", "")).strip()
        if not key:
            continue
        out[key] = {"label": str(d.get("label", "") or "").strip(),
                    "purpose": str(d.get("purpose", "") or "").strip()}
    return out


def outputs(profile: Any) -> List[Dict[str, Any]]:
    """이 키트가 만들 수 있다고 선언한 산출물들. **이름순으로 돌려준다.**

    ⚠️ 선언이 없으면 **빈 목록**이다 — 「전부 가능」이 아니다. 산출물을 선언하지 않은
      키트는 「무엇이 막혔는지」에 답할 수 없고, 답할 수 없음을 그대로 보여야 한다."""
    if not isinstance(profile, dict):
        return []
    return sorted([o for o in (profile.get("outputs") or []) if isinstance(o, dict)],
                  key=lambda o: str(o.get("output", "")))


def resolve(store: Any, kit_id: str, version: str) -> Optional[Dict[str, Any]]:
    """등록된 판본을 찾는다. **모르는 버전은 `None`** — 추측해 최신을 주지 않는다.

    ⚠️ 「없으면 최신으로」는 편해 보이지만, 사용자가 고른 것과 적용된 것이 달라지고
      그 차이는 데이터가 들어간 뒤에야 드러난다."""
    return store.get_kit_version(kit_id, version)
