# -*- coding: utf-8 -*-
"""★★★ 계약형 시연 데이터 **다섯 종만** 합성 인증판으로 승격한다. (§7 2단계)

## 범위 — 셋을 구분한다 (2026-08-20 Supervisor 확정)

    샘플 회사 데이터 생성     기존 전체 데이터셋 **그대로 유지**
    온톨로지 MVP 정본·인증    PRC-02 · LOG-02 · INV-01 · MFG-01 · SLS-01 **만**
    기존 pilot_demo_seed      즉시 교체하지 않고 **호환 유지**

⚠️⚠️ 전체를 한꺼번에 정본으로 올리면, 아직 Resolver·관계·계산이 준비되지 않은 데이터까지
  「공식 경영 의미망에 편입됐다」고 오해하게 된다. 반대로 생성기를 다섯으로 줄이면 기존
  업무 키트와 화면의 데이터가 깨진다. **생성은 그대로 두고 승격만 좁힌다.**

## 「생성됐다」와 「인증됐다」는 다르다

    GENERATED → VALIDATED → RECONCILED → DEMO_CERTIFIED → (온톨로지 색인 가능)

★ 제품에는 이미 이 사슬이 있다(`data_preparation.models`). 그리고 인증 상태의 이름이
  `CERTIFIED` 가 아니라 **`DEMO_CERTIFIED`** 다 — 실제 Data Owner 없이 실적 인증을
  주장하지 않기 위해서다. 그러니 새 상태를 만들지 않는다.

⚠️ **실적 승격 금지는 깃발이 아니라 상태 기계로 보장된다.** `DEMO_CERTIFIED` 에서 갈 수
  있는 곳은 `REVOKED` 뿐이고, 평범한 `CERTIFIED` 라는 상태는 **존재하지 않는다.**

## ⚠️⚠️ 운영 DB 에 쓰지 않는다

이 스크립트는 `data/` 로는 **실행되지 않는다.** 격리된 가상회사 폴더에서만 돈다.
「무효 payload 일 예정이니 괜찮다」는 판단이 과거에 세 번 틀렸다.

LLM 0콜. 같은 seed·같은 프로필이면 **같은 내용 지문**이 나온다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data_preparation import models as m               # noqa: E402
from core.data_preparation import snapshot_service as svc    # noqa: E402
from core.data_preparation.store import DataPreparationStore  # noqa: E402

#: 이 단계의 **정본 원천.** 새 생성기를 만들지 않는다.
GENERATOR = "scripts/generate_sample_company_starter_kit.py"
KIT_ID = "KIT-MFG-NONFERROUS-PROCUREMENT"
KIT_VERSION = "1.0.0"
GENERATOR_SEED = 20260811          # PROFILES 의 고정 seed
PROFILE_NAME = "ontology_vertical_v1"

#: ★★★ 가상회사 인증 원장의 행위자. **실존 인물을 적지 않는다.**
#:
#: ⚠️⚠️ [2026-08-20 Supervisor 지적] 실측용 단일 계정을 쓰는 규칙은 «사람이 쓰는
#:   화면» 을 위한 것이다. 그런데 **인증 원장은 행위의 기록**이다 —
#:   가상회사 자료를 인증한 행위가 실존 인물 이름으로 남으면, 나중에 그 사람이
#:   「이 숫자를 인증했다」고 읽히게 된다.
#: ★ `.invalid` 는 예약 도메인이라 **절대 실재하지 않는다**(RFC 2606).
SYNTHETIC_OWNER = "demo.data.owner@afs.invalid"

#: ★ 최소 경로 4관계가 지나는 다섯 칸. **여기 없는 계약키는 승격하지 않는다.**
VERTICAL: "collections.OrderedDict[str, str]" = collections.OrderedDict([
    ("PRC-02", "po_line_id"),
    ("LOG-02", "shipment_id"),
    ("INV-01", "snapshot_id"),
    ("MFG-01", "plan_line_id"),
    ("SLS-01", "sales_line_id"),
])

#: 관계가 실제로 걸리는 자리. ⚠️ **주문 헤더가 아니라 주문행**이다.
LINK = ("LOG-02", "po_line_id", "PRC-02", "po_line_id")

#: 각 표에서 **비어 있으면 안 되는** 열. 범위 세 값은 공통이다.
REQUIRED = {
    "PRC-02": ("po_line_id", "material_id", "supplier_id", "order_date", "due_date"),
    "LOG-02": ("shipment_id", "po_line_id", "etd", "eta"),
    "INV-01": ("snapshot_id", "snapshot_date", "location_id", "material_id"),
    "MFG-01": ("plan_line_id", "plan_date", "site_id", "product_id"),
    "SLS-01": ("sales_line_id", "customer_id", "product_id", "due_date"),
}
SCOPE_COLUMNS = ("tenant_id", "scope_node_id")


def _read(profile: str, key: str) -> tuple[bytes, list[dict], list[str]]:
    """CSV 원문과 파싱 결과. ★ 원문 그대로를 인증에 넣는다 — 가공하면 지문이 달라진다."""
    path = ROOT / "starter_kits" / KIT_ID / KIT_VERSION / "samples" / profile / f"{key}.csv"
    if not path.exists():
        raise SystemExit(f"✗ 생성기 산출물이 없습니다: {path}\n"
                         f"  먼저 `{GENERATOR}` 를 실행하십시오.")
    payload = path.read_bytes()
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    return payload, rows, list(reader.fieldnames or [])


# ── 무결성 검증 (2-3) ────────────────────────────────────────────────────
def verify(data: dict) -> list[str]:
    """다섯 종의 **관계 무결성**. 문제를 문자열로 모아 돌려준다.

    ⚠️ 「각 데이터셋이 존재하는가」만 보면 안 된다. 존재하는 두 표가 **서로 안 맞는**
      것이 가장 흔하고, 그때 경로는 조용히 빈다."""
    bad: list[str] = []

    for key, pk in VERTICAL.items():
        rows = data[key]["rows"]
        if not rows:
            bad.append(f"{key}: 행이 0건")
            continue

        #: ① 기본키 중복 0건 · ② 필수 열쇠 null 0건
        ids = [str(r.get(pk, "")).strip() for r in rows]
        blank = sum(1 for v in ids if not v)
        if blank:
            bad.append(f"{key}: 기본키 «{pk}» 가 빈 행 {blank}건")
        dup = [v for v, n in collections.Counter(v for v in ids if v).items() if n > 1]
        if dup:
            bad.append(f"{key}: 기본키 중복 {len(dup)}건 (예: {dup[:3]})")

        for col in REQUIRED[key]:
            miss = sum(1 for r in rows if not str(r.get(col, "")).strip())
            if miss:
                bad.append(f"{key}.{col}: 빈 값 {miss}건")

        #: ③ 범위 없는 행 0건 — 범위가 없으면 권한 필터에서 «미기록» 이 되어 통제 밖이다
        for col in SCOPE_COLUMNS:
            miss = sum(1 for r in rows if not str(r.get(col, "")).strip())
            if miss:
                bad.append(f"{key}.{col}: 범위 없는 행 {miss}건")

        #: ④ 다른 tenant 혼입 0건
        tenants = {str(r.get("tenant_id", "")).strip() for r in rows}
        if len(tenants) > 1:
            bad.append(f"{key}: tenant 가 섞여 있음 {sorted(tenants)}")

    #: ⑤ ★★★ **주문행 단위** 관계 — 헤더 단위로 보면 다품목 주문부터 조용히 어긋난다
    child_key, child_col, parent_key, parent_col = LINK
    parents = collections.Counter(
        str(r.get(parent_col, "")).strip() for r in data[parent_key]["rows"])
    orphan, ambiguous = [], []
    for r in data[child_key]["rows"]:
        ref = str(r.get(child_col, "")).strip()
        n = parents.get(ref, 0)
        if n == 0:
            orphan.append(ref)
        elif n > 1:
            ambiguous.append(ref)
    if orphan:
        bad.append(f"{child_key}.{child_col} → {parent_key}: 짝이 없는 행 "
                   f"{len(orphan)}건 (예: {orphan[:3]})")
    if ambiguous:
        bad.append(f"{child_key}.{child_col} → {parent_key}: 짝이 둘 이상인 행 "
                   f"{len(ambiguous)}건 — **정확히 한 건**이어야 한다")

    #: ⑥ 날짜가 시간 순서를 지키는가 — 선적이 주문보다 먼저면 경로의 뜻이 무너진다
    po_date = {str(r.get("po_line_id", "")).strip(): str(r.get("order_date", "")).strip()
               for r in data["PRC-02"]["rows"]}
    early = [str(r.get("shipment_id", "")) for r in data["LOG-02"]["rows"]
             if (od := po_date.get(str(r.get("po_line_id", "")).strip()))
             and str(r.get("etd", "")).strip() and str(r.get("etd", ""))[:10] < od[:10]]
    if early:
        bad.append(f"LOG-02: 주문일보다 이른 출항 {len(early)}건 (예: {early[:3]})")
    return bad


# ── 승격 ─────────────────────────────────────────────────────────────────
def promote(data: dict, data_dir: Path, profile: str, actor: str) -> dict:
    """다섯 종을 인증판으로 만든다. ★ 격리 폴더에서만."""
    workspace = str(data_dir / "raw")
    store = DataPreparationStore(str(data_dir / "data_preparation.db"))

    sample = data["PRC-02"]["rows"][0]
    tenant = str(sample.get("tenant_id", "")).strip()
    #: ⚠️ 조직 범위는 **행이 말하는 것**을 쓴다. 여기서 지어내면 그 순간 자료와 갈라진다.
    scope = str(sample.get("scope_node_id", "")).strip()

    store.upsert_kit_version(
        kit_id=KIT_ID, version=KIT_VERSION, name="비철 조달 샘플 회사",
        mode=m.KIT_MODE_DEMO,
        source_path=f"starter_kits/{KIT_ID}/{KIT_VERSION}/samples/{profile}",
        fingerprint_value=_kit_fingerprint(data),
        profile={"profile_name": PROFILE_NAME, "sample_profile": profile,
                 "generator": GENERATOR, "generator_seed": GENERATOR_SEED,
                 #: ★ 승격 대상을 **여기서도** 못박는다 — 전체 키트는 그대로 두고
                 #:   온톨로지 MVP 대상만 다섯이라는 사실이 등록부에도 남아야 한다.
                 "ontology_vertical_datasets": list(VERTICAL)})
    instance = store.create_instance(
        kit_id=KIT_ID, version=KIT_VERSION, kit_fingerprint=_kit_fingerprint(data),
        tenant_id=tenant, scope_node_id=scope, entity_mode="VIRTUAL",
        label=f"{PROFILE_NAME} ({profile})", created_by=actor)

    out = {}
    for key in VERTICAL:
        binding = store.create_binding(
            instance_id=instance["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT,
            config={"profile": PROFILE_NAME, "source": f"samples/{profile}/{key}.csv"},
            tenant_id=tenant, scope_node_id=scope, entity_mode="VIRTUAL",
            created_by=actor)
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            binding = store.transition(binding["binding_id"], target)

        snap = svc.ingest(store, binding=binding, payload=data[key]["payload"],
                          file_name=f"{key}.csv", workspace_root=workspace,
                          created_by=actor, data_kind=m.DATA_KIND_DEMO)
        rows, cols = data[key]["rows"], data[key]["columns"]
        #: ★ 대사 기준은 **원천 행 수**다. 「셀 것이 없으면 통과」로 두면 대사가 사라진다.
        final = svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                                 control={"row_count": len(rows)})
        out[key] = final
    return {"instance": instance, "snapshots": out, "tenant": tenant, "scope": scope}


def _kit_fingerprint(data: dict) -> str:
    """다섯 원문의 **내용 지문.** 같은 seed 면 같아야 한다."""
    h = hashlib.sha256()
    for key in VERTICAL:
        h.update(key.encode())
        h.update(hashlib.sha256(data[key]["payload"]).digest())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="계약형 시연 데이터 다섯 종 합성 인증 승격")
    ap.add_argument("--data-dir", required=True,
                    help="격리된 가상회사 폴더. ⚠️ 운영 `data/` 는 거부한다")
    ap.add_argument("--profile", choices=("quick", "full"), default="quick")
    ap.add_argument("--actor", default=SYNTHETIC_OWNER,
                    help="합성 인증 행위자. ⚠️ 실존 계정을 넣지 마십시오")
    ap.add_argument("--verify-only", action="store_true",
                    help="검증만 하고 아무것도 쓰지 않는다")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    operational = (ROOT / "data").resolve()
    #: ⚠️⚠️ 운영 폴더로는 **절대** 돌지 않는다. 하위 폴더도 막는다.
    if data_dir == operational or operational in data_dir.parents:
        print(f"✗ 운영 데이터 폴더에는 쓰지 않습니다: {data_dir}")
        print("  · 격리된 가상회사 폴더를 주십시오.")
        return 2

    data = {}
    for key in VERTICAL:
        payload, rows, columns = _read(args.profile, key)
        data[key] = {"payload": payload, "rows": rows, "columns": columns,
                     "checksum": hashlib.sha256(payload).hexdigest()}

    print(f"=== 원천 ({args.profile}) ===")
    for key, pk in VERTICAL.items():
        print(f"  {key:8s} {len(data[key]['rows']):>6,}행  열쇠={pk:14s} "
              f"sha256={data[key]['checksum'][:16]}")
    print(f"  키트 지문 {_kit_fingerprint(data)[:32]}")
    print()

    print("=== 관계 무결성 ===")
    bad = verify(data)
    if bad:
        for b in bad:
            print(f"  ✗ {b}")
        print(f"\n✗ 검증 실패 {len(bad)}건 — **승격하지 않습니다.**")
        return 1
    child, ccol, parent, pcol = LINK
    print(f"  ● 기본키 중복 0 · 필수 열쇠 빈 값 0 · 범위 없는 행 0 · tenant 혼입 0")
    print(f"  ● {child}.{ccol} → {parent}.{pcol} 주문**행** 단위로 정확히 1:1")
    print(f"  ● 주문일보다 이른 출항 0건")
    print()

    if args.verify_only:
        print("=== 검증만 수행했습니다(아무것도 쓰지 않음) ===")
        return 0

    os.makedirs(data_dir, exist_ok=True)
    result = promote(data, data_dir, args.profile, args.actor)

    print("=== 인증판 ===")
    ok = True
    for key, snap in result["snapshots"].items():
        state = snap["state"]
        mark = "●" if state == m.DEMO_CERTIFIED else "✗"
        ok = ok and state == m.DEMO_CERTIFIED
        print(f"  {mark} {key:8s} {snap['snapshot_id']}  {state:15s} "
              f"{snap['row_count']:>6,}행  {snap['data_kind']}")
        if state == m.QUARANTINED:
            print(f"      격리 사유: {snap.get('quarantine_json')}")
    print()

    manifest = {
        "profile_name": PROFILE_NAME,
        "generator": GENERATOR, "generator_seed": GENERATOR_SEED,
        "kit_id": KIT_ID, "kit_version": KIT_VERSION, "sample_profile": args.profile,
        "kit_fingerprint": _kit_fingerprint(data),
        "tenant_id": result["tenant"], "scope_node_id": result["scope"],
        "entity_mode": "VIRTUAL",
        "instance_id": result["instance"]["instance_id"],
        "certified_by": args.actor,
        "data_kind": m.DATA_KIND_DEMO,
        #: ★ 실적 승격 금지는 **깃발이 아니라 상태 기계**로 보장된다.
        "promotable_to_real": False,
        "promotion_guard": (
            f"«{m.DEMO_CERTIFIED}» 에서 갈 수 있는 상태는 "
            f"{list(m.SNAPSHOT_TRANSITIONS[m.DEMO_CERTIFIED])} 뿐이며, "
            f"평범한 CERTIFIED 상태는 존재하지 않는다."),
        "datasets": {
            key: {"primary_key": pk, "rows": len(data[key]["rows"]),
                  "source_checksum": data[key]["checksum"],
                  "snapshot_id": result["snapshots"][key]["snapshot_id"],
                  "state": result["snapshots"][key]["state"],
                  "content_fingerprint": result["snapshots"][key]["content_fingerprint"]}
            for key, pk in VERTICAL.items()},
    }
    path = data_dir / f"{PROFILE_NAME}.manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"· 계보 기록 {path}")
    print()
    print("=== " + ("다섯 종이 모두 합성 인증되었습니다 ==="
                    if ok else "일부가 인증되지 않았습니다 ==="))
    #: ⚠️ 여기까지가 2단계다. **Dataset Resolver 와 온톨로지 관계 설치는 하지 않는다.**
    print("⚠️ 이 단계는 인증까지입니다 — 범위 색인·Resolver·관계 설치는 아직입니다.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
