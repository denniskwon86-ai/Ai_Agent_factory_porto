"""정본 키트 합성 샘플로 인증 대상 판을 만드는 시험 도우미. 운영 데이터·키·실사용자 없음.

## 왜 필요한가 (2026-09-25)

인증이 이제 **설치가 고정한 데이터셋 계약**과 판의 봉인 원문을 대조한다
(`certification_subject._conforming_contract`). 종전 fixture 의 `amount` 한 칸·`a` 한 칸
판은 정본 계약과 맞지 않아 막힌다 — 막혀야 맞다. 그래서 시험 판도 정본으로 만든다.

- 자료: 키트 정본 합성 샘플(`starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/samples/quick`).
  열·순서·업무키는 정본 계약과 같다. 바꾸는 것은 행 안의 `tenant_id`·`scope_node_id` 두 칸뿐이다.
- RAW 뿌리: 제품 업로드와 같은 `data_path("data_preparation")`. 격리 러너·conftest 가 `DATA_DIR`
  을 실행 루트로 돌린다. ⚠️ 그래도 **운영 `data/` 가 아닌지 먼저 단언한다** — 기준은
  `PROJECT_ROOT` 이다(격리가 `DATA_DIR` 을 돌리면 `DATA_DIR` 기준 판정은 뒤집힌다).
- 설치: 계약을 싣는 팩(`process_pack_artifacts.CANDIDATE_MANIFEST`, 1.2.0)을 실제로 고정한다
  (`process_kit_instances.create_or_get`). 등록부 키트는 고정 계약이 없어 인증이 막힌다.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "starter_kits" / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.0.0"
SAMPLE_ROWS = 3
SCOPE_COLUMNS = ("tenant_id", "scope_node_id")


def canonical_contract(key):
    return json.loads((KIT / "contracts" / f"{key}.contract.json").read_text(encoding="utf-8-sig"))


def canonical_fields(key):
    return [f["name"] for f in canonical_contract(key)["schema"]["fields"]]


def sample_table(key, context, *, offset=0, rows=SAMPLE_ROWS):
    """정본 샘플의 `[offset, offset+rows)` 행. 조직 범위 두 칸만 시험 문맥으로 다시 묶는다."""
    with (KIT / "samples" / "quick" / f"{key}.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        picked = [dict(row) for index, row in enumerate(reader) if offset <= index < offset + rows]
    assert columns == canonical_fields(key), f"{key}: 샘플 열이 정본 계약과 다르다"
    assert len(picked) == rows, f"{key}: 샘플 행이 모자란다"
    for row in picked:
        row.update({name: str(context[name]) for name in SCOPE_COLUMNS})
    return columns, picked


def to_csv(columns, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def raw_root() -> str:
    """제품 업로드와 같은 RAW 뿌리. **운영 `data/` 이면 멈춘다.**"""
    from core.paths import PROJECT_ROOT, data_path
    root = Path(data_path("data_preparation")).resolve()
    operational = (Path(PROJECT_ROOT) / "data").resolve()
    assert root != operational and not root.is_relative_to(operational), \
        f"RAW 뿌리가 운영 data/ 다 — 격리되지 않은 실행이다: {root}"
    return str(root)


def ingest_sample(store, binding, key, context, *, offset=0, rows=SAMPLE_ROWS, created_by="", extra=None,
                  data_kind=None):
    """제품 수집(`snapshot_service.ingest`)으로 판을 만든다. 인증 단계가 쓸 파싱 행도 돌려준다.

    `extra` 는 정본 열 **뒤에 붙는** 추가 열이다(`{이름: 값}`). 계약 대조는 «필수 ⊆ 열» 이라
    추가 열은 통과한다 — «나중에 스키마가 달라진 판» 을 정본을 깨지 않고 만들 때 쓴다."""
    from core.data_preparation import models as m, snapshot_service as ss
    columns, table = sample_table(key, context, offset=offset, rows=rows)
    for name, value in (extra or {}).items():
        assert name not in columns, f"{name}: 정본 열을 덮어쓰지 않는다"
        columns.append(name)
        for row in table:
            row[name] = str(value)
    payload = to_csv(columns, table)
    snapshot = ss.ingest(store, binding=binding, payload=payload, file_name=f"{key}.csv",
                         workspace_root=raw_root(), created_by=created_by,
                         data_kind=data_kind or m.DATA_KIND_REAL)
    parsed = ss.parse_csv(payload, file_name=f"{key}.csv")
    assert parsed.columns == columns and parsed.rows == table
    return snapshot, parsed


def pinned_instance(store, *, context, context_root_id, actor, operation_id):
    """계약을 싣는 팩(1.2.0)을 **실제로 고정한** 인스턴스. 설치 서비스의 B2 결속 경로를 쓴다."""
    from core.data_preparation import process_kit_instances as pki
    from core.data_preparation.process_pack_artifacts import CANDIDATE_MANIFEST, load_bundle
    from core.enterprise_context.process_schema import ProcessBoundary
    bundle = load_bundle(CANDIDATE_MANIFEST)
    assert bundle.get("dataset_contracts"), "후보 팩이 데이터셋 계약을 싣지 않는다"
    scope = context["scope_node_id"]
    boundary = ProcessBoundary(tenant_id=context["tenant_id"], context_root_id=context_root_id,
                               entity_mode=context["entity_mode"],
                               scope_node_id="" if scope == context_root_id else scope)
    return pki.create_or_get(store, operation_id=operation_id, bundle=bundle, boundary=boundary, actor=actor)
