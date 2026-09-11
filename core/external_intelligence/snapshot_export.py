"""[F-3] 승격된 관측값 → **업무키트 Snapshot**. 두 평면을 잇는 마지막 고리.

## 왜 이 모듈인가 — 선택지 B 를 고른 이유

F-0 탐침이 「수집 → 생성」 사이가 끊겨 있다고 했다. 파고드니 **연결은 이미 선언돼
있었다** — `app_release_dataset_bindings` 가 `EXT-01/02/03` 을 「전사 실적으로 읽겠다」고
10건 적어 뒀다. 막고 있던 것은 한 줄이었다:

    core/data_preparation/models.py
      MATERIALIZABLE_PROVIDERS = (FILE_SNAPSHOT, AFS_NATIVE)   ← CONNECTOR_QUERY 가 없다

선택지는 둘이었다.

    A  `CONNECTOR_QUERY` 를 구현한다        최신성은 좋지만 「그 계획이 «당시» 어떤 값을
                                            썼나」가 흔들린다
    B  승격된 관측값을 **스냅샷으로 떨어뜨려** 기존 `FILE_SNAPSHOT` 경로에 태운다
                                            ⭐ 재현성과 인증 상태가 **이미 보장된다**

**B 로 정했다**(사용자 결정 2026-09-11 · Codex 권고와 일치). 근거는 Codex 의 문장이
정확했기 때문이다 — 「격리 적재본을 앱에 **직접 개방**하는 것이 아니라, 검토·인증한
전사 공통 자료를 앱의 **데이터 계약으로 연결**한다」.

## ★★★ 이 모듈이 «만들지 않는» 것

**새 어휘를 하나도 만들지 않는다.** 새 provider·새 상태·새 결속 종류가 없다.

  · `EXT-02` 의 `FILE_SNAPSHOT` 결속은 **이미 있고 ACTIVE 다**(`sb_c586cfaf6bb442`)
  · CSV 20열은 **정본 스냅샷의 `schema_json` 에서 가져왔다** — 내 말로 쓰지 않았다
    (기억: fixture 를 내 말로 쓰면 100% 초록인데 정본으로는 안 돈다)
  · 파이프라인은 기존 `snapshot_service` 를 그대로 부른다

## ⚠️⚠️ 어디서 멈추는가 — 이것이 이 모듈의 가장 중요한 사실

실물 데이터(`data_kind=REAL`)는 **인증 종점에 도달할 수 없다.**

    RAW → PROFILED → STANDARDIZED → RECONCILED → ✋ 여기서 멈춘다
                                                  DEMO_CERTIFIED 는 REAL 을 거부한다

`certify_demo()` 가 그렇게 적어 뒀다: 「«REAL» 데이터에는 시연 인증을 붙이지 않습니다 —
시연 자료와 실제 실적이 섞이면 어느 것이 시연이었는지 가릴 수 없습니다.」

★ 그래서 이 모듈은 **`certify_demo` 를 부르지 않는다.** 부르면 예외가 나고, 예외를
  삼키면 「실패했는데 성공처럼 보이는」 경로가 된다. 대신 `RECONCILED` 에서 **의도적으로
  멈추고 그 사실을 결과에 싣는다.**

⚠️ 즉 **B 를 골라도 실물 데이터는 앱까지 흐르지 않는다.** 흐르게 하려면 인증 종점을
  하나 더 여는 **별도 결정**이 필요하다(실제 Data Owner 의 실적 인증). 그것은 제품·조직
  결정이지 코드 결정이 아니다.

LLM 0콜.
"""
from __future__ import annotations

import csv
import hashlib
import io
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CONTRACT_KEY = "EXT-02"

#: ★★★ 정본 스냅샷 `ds_f0ee93365f3747` 의 `schema_json` 에서 «그대로» 옮긴 20열.
#:   순서까지 같다 — 열 순서가 다르면 checksum 이 달라지고 「같은 자료인가」 비교가 깨진다.
#: ⚠️ 여기를 손으로 늘리지 말 것. 계약이 바뀌면 정본 스냅샷을 먼저 보고 맞춘다.
EXT02_COLUMNS: Tuple[str, ...] = (
    "record_id", "tenant_id", "scope_node_id", "data_class", "business_data_kind",
    "data_origin", "quality_status", "certification_status", "as_of_date", "lineage_id",
    "observation_id", "commodity_code", "observed_at", "published_at", "vintage_date",
    "value", "unit", "currency", "source_id", "trust_grade",
)

#: 성격 값. ⚠️ 시연 자료의 `SYNTHETIC` 을 **쓰지 않는다** — 그것이 T-2 가 막는 바로 그 혼합이다.
DATA_CLASS = "PUBLIC_DISCLOSED"
DATA_ORIGIN = "PUBLIC_DISCLOSED"
BUSINESS_DATA_KIND = "REFERENCE"
QUALITY_STATUS = "PASS"
#: ⚠️ `CERTIFIED_FOR_DEMO` 가 아니다. 실물은 아직 인증 종점이 없다 — 그 사실을 값으로 남긴다.
CERTIFICATION_STATUS = "UNCERTIFIED"

#: 멈추는 곳. 실물 데이터의 «정상» 종점이다.
TERMINAL_STATE_FOR_REAL = "RECONCILED"


class SnapshotExportError(ValueError):
    pass


def _row_id(observation_id: str) -> str:
    """결정론적 record_id. **같은 관측값은 같은 행**이 되어 중복 적재를 막는다."""
    digest = hashlib.sha256(str(observation_id).encode("utf-8")).hexdigest()[:12]
    return "ext-02-%s" % digest


def build_rows(observations: Sequence[Mapping[str, Any]], *,
               tenant_id: str, scope_node_id: str,
               as_of_date: str) -> List[Dict[str, str]]:
    """관측값 → 계약 행. **순수 함수** — 저장소를 만지지 않는다.

    ⚠️ 값이 없는 관측값은 **건너뛰지 않고 거부한다.** 조용히 빼면 행 수가 줄고,
      그 스냅샷은 「원천보다 작은 판」이 되는데 아무도 모른다."""
    rows: List[Dict[str, str]] = []
    for obs in observations:
        oid = str(obs.get("observation_id") or "").strip()
        if not oid:
            raise SnapshotExportError("관측값에 observation_id 가 없습니다 — 업무 키가 없으면 "
                                      "같은 값이 두 번 들어와도 알 수 없습니다.")
        if obs.get("value") is None:
            raise SnapshotExportError(f"{oid} 에 값이 없습니다 — 빈 값을 0 으로 채우지 않습니다.")
        code = str(obs.get("indicator_code") or "").strip()
        if not code:
            #: ★★★ [2026-09-11] 실제 저장소의 관측값 행에는 `indicator_code` 가 «없다» —
            #:   `indicator_id`(`ind_…`)만 있다. 그대로 두면 `commodity_code` 가 **조용히
            #:   빈 값**이 되고, 그 판은 「품목을 모르는 원자재 가격」이 된다.
            #:   ⚠️ 호출부가 지표 코드를 **붙여서** 넘겨야 한다. 여기서 id→코드를 조회하지
            #:     않는 이유는, 이 함수가 순수해야 시험이 저장소 없이 돌기 때문이다.
            raise SnapshotExportError(
                f"{oid} 에 indicator_code 가 없습니다 — 품목을 모르는 가격 행을 만들지 "
                f"않습니다. 저장소의 관측값 행에는 indicator_id 만 있으므로 호출부가 "
                f"코드를 붙여 넘기십시오.")
        rows.append({
            "record_id": _row_id(oid),
            "tenant_id": tenant_id,
            "scope_node_id": scope_node_id,
            "data_class": DATA_CLASS,
            "business_data_kind": BUSINESS_DATA_KIND,
            "data_origin": DATA_ORIGIN,
            "quality_status": QUALITY_STATUS,
            "certification_status": CERTIFICATION_STATUS,
            "as_of_date": as_of_date,
            #: 계보 — 관측값 id 에서 유도한다. uuid 를 새로 뽑으면 두 번 내보낼 때
            #: 같은 자료인데 계보가 달라져 「다른 판」으로 보인다.
            "lineage_id": "lin-%s" % hashlib.sha256(oid.encode("utf-8")).hexdigest()[:12],
            "observation_id": oid,
            #: ★ 지표 코드(`WB_COPPER`)에서 품목을 뗀다. 계약의 열 이름이 `commodity_code` 다.
            "commodity_code": code.split("_", 1)[1] if "_" in code else code,
            "observed_at": str(obs.get("observed_at") or ""),
            #: ⚠️ Pink Sheet 는 값별 발표일을 주지 않는다 — **지어내지 않고 비운다.**
            "published_at": str(obs.get("published_at") or ""),
            "vintage_date": str(obs.get("vintage") or ""),
            "value": str(obs.get("value")),
            "unit": str(obs.get("unit") or ""),
            "currency": str(obs.get("currency") or ""),
            "source_id": str(obs.get("source_id") or ""),
            "trust_grade": str(obs.get("grade") or ""),
        })
    return rows


def to_csv(rows: Sequence[Mapping[str, str]]) -> bytes:
    """계약 열 순서대로 CSV 로 만든다. **줄바꿈을 고정한다** — 플랫폼마다 달라지면
    같은 자료인데 checksum 이 달라진다."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(EXT02_COLUMNS),
                            extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in EXT02_COLUMNS})
    return buf.getvalue().encode("utf-8")


def control_totals(rows: Sequence[Mapping[str, str]]) -> Dict[str, Any]:
    """원천이 말하는 합계. 대사(`reconcile`)가 이것과 «우리가 센 값» 을 맞춘다.

    ★ 우리가 만든 파일이라 늘 맞을 것 같지만, **맞는지 확인하는 것이 요점이다** —
      직렬화·인코딩·잘림에서 어긋나면 여기서 드러난다."""
    total = 0.0
    for r in rows:
        raw = str(r.get("value", "")).strip()
        if raw:
            total += float(raw)
    return {"row_count": len(rows), "sums": {"value": round(total, 6)}}


def export(store: Any, *, binding: Mapping[str, Any],
           observations: Sequence[Mapping[str, Any]],
           workspace_root: str, created_by: str,
           as_of_date: str, file_name: str = "") -> Dict[str, Any]:
    """승격된 관측값을 **기존 FILE_SNAPSHOT 경로**에 태운다.

    ★★★ `certify_demo` 를 **부르지 않는다.** 실물 데이터는 거기서 거부되고, 예외를
      삼키면 「실패했는데 성공처럼 보이는」 경로가 된다. `RECONCILED` 에서 의도적으로
      멈추고 그 사실을 결과에 싣는다 — 화면이 「왜 인증이 안 됐나」에 답할 수 있게.

    ⚠️ `data_kind` 를 인자로 받지 않는다. 이 경로로 들어오는 것은 **언제나 실물**이고,
      고를 수 있게 두면 언젠가 실물이 시연으로 적재된다."""
    from core.data_preparation import models as m
    from core.data_preparation import snapshot_service as svc

    if str(binding.get("provider") or "") != m.PROVIDER_FILE_SNAPSHOT:
        raise SnapshotExportError(
            f"{m.PROVIDER_FILE_SNAPSHOT} 결속에만 내보냅니다(받은 값: "
            f"{binding.get('provider')!r}) — 선택지 B 는 «기존 경로를 그대로 쓴다» 가 요점입니다.")
    if str(binding.get("dataset_contract_key") or "") != CONTRACT_KEY:
        raise SnapshotExportError(
            f"이 내보내기는 {CONTRACT_KEY} 전용입니다(받은 값: "
            f"{binding.get('dataset_contract_key')!r}) — 다른 계약에 넣으면 계약이 거짓말을 합니다.")
    if not observations:
        raise SnapshotExportError("승격된 관측값이 0건입니다 — 빈 판을 만들지 않습니다.")

    rows = build_rows(observations,
                      tenant_id=str(binding.get("tenant_id") or ""),
                      scope_node_id=str(binding.get("scope_node_id") or ""),
                      as_of_date=as_of_date)
    payload = to_csv(rows)
    name = file_name or "%s__%s.csv" % (CONTRACT_KEY, as_of_date)

    snapshot = svc.ingest(store, binding=dict(binding), payload=payload, file_name=name,
                          workspace_root=workspace_root, created_by=created_by,
                          data_kind=m.DATA_KIND_REAL)
    sid = snapshot["snapshot_id"]
    columns = list(EXT02_COLUMNS)

    row = svc.profile(store, sid, rows, columns)
    if row["state"] == m.QUARANTINED:
        return _result(row, rows, stopped="PROFILED 에서 격리됨")
    row = svc.standardize(store, sid, rows)
    if row["state"] == m.QUARANTINED:
        return _result(row, rows, stopped="STANDARDIZED 에서 격리됨")
    row = svc.reconcile(store, sid, rows, control_totals(rows))
    if row["state"] == m.QUARANTINED:
        return _result(row, rows, stopped="대사 불일치로 격리됨")
    return _result(row, rows, stopped="")


def _result(row: Mapping[str, Any], rows: Sequence[Mapping[str, str]],
            *, stopped: str) -> Dict[str, Any]:
    quarantined = str(row.get("state")) == "QUARANTINED"
    return {
        "snapshot_id": row.get("snapshot_id"),
        "state": row.get("state"),
        "data_kind": row.get("data_kind"),
        "row_count": len(rows),
        "checksum": row.get("checksum"),
        "quarantined": quarantined,
        "stopped_reason": stopped,
        #: ★ 여기가 이 모듈의 «정직한 한계» 다. 화면이 이 문장을 그대로 보여 주면
        #:   사용자는 「왜 인증이 안 됐나」를 묻지 않는다.
        "certification_note": (
            "실물 데이터(REAL)는 RECONCILED 가 종점입니다 — 이 저장소의 유일한 인증 종점인 "
            "DEMO_CERTIFIED 는 시연 자료 전용이고, 실물에 붙이면 시연과 실적을 가릴 수 없게 "
            "됩니다. 실물을 앱까지 흘리려면 실제 Data Owner 의 실적 인증 종점을 여는 "
            "별도 결정이 필요합니다."
            if not quarantined else
            "격리된 판은 인증 대상이 아닙니다. 고친 파일은 «새 Snapshot» 으로 다시 넣습니다."),
    }


def certify_source(store: Any, snapshot_id: str, *, source_id: str,
                   certified_by: str) -> Dict[str, Any]:
    """승인된 **공개 원천**의 실물 판을 인증한다 — `SOURCE_CERTIFIED`.

    ## ⚠️⚠️ 이것은 «회사 실적» 인증이 아니다

        DEMO_CERTIFIED     시연 자료
        SOURCE_CERTIFIED   **출처가 우리가 아닌** 공표 자료      ← 이 함수가 여는 것
        (없음)             회사 실적(자사 매출·원가·생산)        ← 여전히 종점이 없다

    ★★★ 회사 실적에는 종점을 **열지 않았다.** 그것은 실제 Data Owner 가 「이 숫자가
      맞다」고 서명하는 일이고, 서명자가 없는 상태에서 열면 시연 자료를 실적으로 읽게
      만드는 바로 그 사고가 난다. 여기서 여는 것은 **발행 기관이 따로 있는** 자료뿐이고,
      우리 쪽 책임은 「그 출처를 쓰기로 승인했는가」 하나다.

    ## 왜 이 함수가 `snapshot_service` 가 아니라 여기 있나

    ★ 「원천이 승인됐는가」는 `external_sources` 를 봐야 알고, 그 등록부는 이 레인에 있다.
      `data_preparation` 이 여기를 import 하면 순환이 된다. 그래서 **정책은 이쪽, 상태와
      전이는 저쪽**으로 나눴다 —
      `advance_snapshot()` 이 「RECONCILED 에서만·REAL 자료만」을 스스로 지키고(저장소가
      자기 상태를 지킨다), 이 함수가 「승인된 원천인가」를 더한다.
      ⚠️ 층마다 가정이 달라야 층이다 — 한쪽이 다른 쪽을 믿으면 층이 아니라 껍데기다."""
    from core.data_preparation import models as m
    from core.external_intelligence import external_intelligence as intel

    if not str(certified_by or "").strip():
        raise SnapshotExportError(
            "certified_by 는 필수입니다 — 누가 이 판을 인증했는지 없으면 근거가 없습니다.")
    sid = str(source_id or "").strip()
    if not sid:
        raise SnapshotExportError(
            "source_id 는 필수입니다 — 어느 원천에서 온 판인지 모르면 «승인된 출처인가» 를 "
            "물을 수 없습니다.")
    src = intel.get_source(sid)
    if src is None:
        raise SnapshotExportError(f"존재하지 않는 원천입니다: {sid}")
    if not src.get("enabled"):
        raise SnapshotExportError(
            f"승인되지 않은 원천입니다: {sid}(승인자 없음) — 원천 승인은 「이 출처의 값을 "
            f"회사 계획에 쓴다」는 사람의 결정이고, 그것 없이 인증하면 이 판의 근거가 "
            f"«아무도 하지 않은 승인» 이 됩니다.")

    row = store.get_snapshot(snapshot_id)
    if row is None:
        raise SnapshotExportError(f"존재하지 않는 Snapshot 입니다: {snapshot_id}")
    #: ⚠️ [2026-09-11] 처음엔 `certified_by` 를 «결과에만» 담고 저장하지 않았다 —
    #:   인자로 받아 놓고 버린 것이다. 사용자가 「내가 인증한다」고 해도 이름이
    #:   남을 자리가 없었다. 저장소가 이제 이 값을 «요구» 한다.
    out = store.advance_snapshot(snapshot_id, m.SOURCE_CERTIFIED,
                                 certified_by=certified_by)
    return {
        "snapshot_id": out.get("snapshot_id"),
        "state": out.get("state"),
        "data_kind": out.get("data_kind"),
        "certified_at": out.get("certified_at"),
        "source_id": sid,
        "source_approved_by": src.get("approved_by"),
        "certified_by": out.get("certified_by"),
        "note": ("이 판은 «발행 기관이 따로 있는 공표 자료» 로 인증됐습니다 — "
                 "회사 실적 인증이 아닙니다. 원천 승인자는 "
                 f"{src.get('approved_by')} 입니다."),
    }
