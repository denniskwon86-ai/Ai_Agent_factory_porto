"""[BDR-3] L0 파일 Snapshot — 파일 하나가 **믿을 수 있는 표**가 되기까지.

```text
RAW → PROFILED → STANDARDIZED → RECONCILED → DEMO_CERTIFIED
                                           ↘ QUARANTINED
```

## 이 파일이 막으려는 세 가지

★★★ **① 실패를 0행으로 저장하지 않는다.**
  파싱이 깨졌는데 「0행 Snapshot」을 남기면, 그것은 「데이터가 없다」로 읽힌다. 그 위에서
  계산이 돌면 **합계가 0인 보고서**가 나오고, 아무도 그것이 고장이라고 생각하지 않는다.

★★★ **② 잘린 파일을 전체로 저장하지 않는다.**
  읽다가 끊긴 파일은 「일부」이지 「작은 파일」이 아니다. 원천 control total 과 대사해
  **행 수·합계가 맞지 않으면 격리**한다.

★★★ **③ 파일명·경로로 원천을 믿지 않는다.**
  `purchase_orders_2026.csv` 라는 이름은 아무것도 보증하지 않는다. 믿는 것은 **내용의
  SHA-256** 이고, 어느 계약에 붙는지는 사람이 결속으로 정한다.

## 시연 인증의 의미

⚠️⚠️ 실제 Data Owner 가 없으므로 `CERTIFIED ACTUAL` 을 **주장하지 않는다.** 인증은
  `DEMO_CERTIFIED` 이고 `data_kind` 는 `DEMO/SYNTHETIC` 이다. 시연 자료를 검증된
  실적으로 읽는 순간, 그 숫자로 경영 판단을 하는 경로가 열린다.
"""
import csv
import hashlib
import io
import os
import re
import shutil
from datetime import datetime, timezone
from typing import (Any, Dict, List, Mapping,
                    NamedTuple, Optional, Tuple)

from core.data_preparation import models as m

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: 불변 RAW 영역. 여기에 들어간 파일은 **다시 쓰지 않는다.**
RAW_DIRNAME = "raw"

#: 시연 범위는 CSV 우선. ⚠️ XLSX 는 기존 파서가 안정적일 때만 더한다 — 「일단
#:   넣고 되는 만큼」은 잘린 표를 전체로 읽는 가장 흔한 길이다.
ALLOWED_SUFFIXES: Tuple[str, ...] = (".csv",)

_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?")


class IngestError(m.DataPreparationError):
    """파일을 표로 만들 수 없다 — **Snapshot 을 만들지 않는다.**"""


class ParsedFile(NamedTuple):
    rows: List[Dict[str, str]]
    columns: List[str]
    checksum: str
    byte_size: int


def raw_dir(root: str) -> str:
    return os.path.join(root or ".", RAW_DIRNAME)


def checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def infer_type(values: List[str]) -> str:
    """열의 형을 **관측된 값에서** 추정한다.

    ⚠️ 값이 하나도 없으면 `unknown` 이다 — `string` 으로 두면 「빈 열」과 「글자
      열」이 같아지고, 나중에 숫자를 넣으려다 형이 안 맞는 이유를 못 찾는다."""
    seen = [v for v in values if str(v).strip() != ""]
    if not seen:
        return "unknown"
    if all(_NUMERIC.match(v.strip()) for v in seen):
        return "number"
    if all(_DATE.match(v.strip()) for v in seen):
        return "datetime"
    return "string"


def parse_csv(payload: bytes, *, file_name: str = "") -> ParsedFile:
    """바이트 → 표. **던진다** — 되는 만큼 읽지 않는다.

    ⚠️ 여기서 예외를 삼키고 빈 표를 돌려주면 위 ①(실패를 0행으로) 이 그대로 일어난다."""
    suffix = os.path.splitext(str(file_name or ""))[1].lower()
    if suffix and suffix not in ALLOWED_SUFFIXES:
        raise IngestError(
            f"지금은 {list(ALLOWED_SUFFIXES)} 만 읽습니다(받은 것: {suffix}) — "
            f"파서가 확실하지 않은 형식을 «되는 만큼» 읽으면 잘린 표가 전체로 들어옵니다.")
    if not payload:
        raise IngestError("파일이 비어 있습니다 — 빈 파일과 «0행 표» 는 다릅니다.")

    #: ⚠️ NUL 은 CSV 에 나오지 않는다. 이 검사가 없으면 이진 파일이 «UTF-8 로는
    #:   읽히는» 쓰레기가 되어 「데이터 행이 없습니다」로 빠지고, 사유가 틀린 채
    #:   막힌다 — 막히긴 하지만 사용자는 파일이 잘못된 줄 모른다.
    if b"\x00" in payload:
        raise IngestError("이진 파일로 보입니다(NUL 바이트) — CSV 가 아닙니다.")

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise IngestError(f"UTF-8 로 읽을 수 없습니다: {str(e)[:100]}")

    try:
        reader = csv.DictReader(io.StringIO(text))
        columns = list(reader.fieldnames or [])
        rows = [{k: ("" if v is None else str(v)) for k, v in r.items() if k is not None}
                for r in reader]
    except csv.Error as e:
        raise IngestError(f"CSV 를 읽을 수 없습니다: {str(e)[:100]}")

    if not columns:
        raise IngestError("머리글이 없습니다 — 열 이름 없이는 어느 값이 무엇인지 알 수 없습니다.")
    if not rows:
        #: ⚠️ 「머리글만 있는 파일」은 **데이터가 없는 것**이지 0행 표가 아니다. 사람이
        #:   잘못된 파일을 올린 것에 가깝고, 통과시키면 합계 0 보고서가 된다.
        raise IngestError("데이터 행이 없습니다 — 머리글만 있는 파일은 받지 않습니다.")
    return ParsedFile(rows=rows, columns=columns, checksum=checksum_bytes(payload),
                      byte_size=len(payload))


def store_raw(root: str, snapshot_id: str, payload: bytes, file_name: str) -> str:
    """원본을 **불변 RAW 영역**에 둔다. 이미 있으면 덮지 않는다.

    ⚠️ 덮어쓰기를 허용하면 checksum 은 그대로인데 파일이 달라질 수 있고, 그러면
      「지문이 맞으니 같은 파일」이라는 전제가 깨진다."""
    d = raw_dir(root)
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", os.path.basename(file_name or "file"))[:80]
    path = os.path.join(d, f"{snapshot_id}__{safe}")
    if os.path.exists(path):
        raise IngestError(f"이미 있는 RAW 파일입니다: {os.path.basename(path)}")
    with open(path, "wb") as f:
        f.write(payload)
    return path


def verify_raw(path: str, expected_checksum: str) -> bool:
    """보관된 원본이 **그때 그 파일인가.** Gate D 의 「RAW checksum 재현」."""
    try:
        with open(path, "rb") as f:
            return checksum_bytes(f.read()) == str(expected_checksum or "")
    except Exception:
        return False


def ingest(store: Any, *, binding: Dict[str, Any], payload: bytes, file_name: str,
           workspace_root: str, created_by: str = "",
           data_kind: str = m.DATA_KIND_DEMO) -> Dict[str, Any]:
    """파일 → `RAW` Snapshot. **파싱에 실패하면 아무것도 남기지 않는다.**

    ★ 순서가 중요하다: **먼저 파싱하고** 그다음에 Snapshot 을 만든다. 반대로 하면
      실패했을 때 「0행 Snapshot」이 남는다."""
    parsed = parse_csv(payload, file_name=file_name)      # ← 실패하면 여기서 끝난다

    snapshot = store.create_snapshot(
        binding_id=str(binding.get("binding_id", "")),
        instance_id=str(binding.get("instance_id", "")),
        dataset_contract_key=str(binding.get("dataset_contract_key", "")),
        checksum=parsed.checksum, byte_size=parsed.byte_size,
        row_count=len(parsed.rows),
        schema=[{"name": c, "type": infer_type([r.get(c, "") for r in parsed.rows])}
                for c in parsed.columns],
        content_fingerprint=parsed.checksum, data_kind=data_kind,
        tenant_id=str(binding.get("tenant_id", "")),
        scope_node_id=str(binding.get("scope_node_id", "")),
        entity_mode=str(binding.get("entity_mode", "")),
        created_by=created_by)

    path = store_raw(workspace_root, snapshot["snapshot_id"], payload, file_name)
    with store.transaction() as conn:
        conn.execute("UPDATE dataset_snapshots SET raw_path=? WHERE snapshot_id=?",
                     (path, snapshot["snapshot_id"]))
    return store.get_snapshot(snapshot["snapshot_id"])


# ── 프로파일 ─────────────────────────────────────────────────────────────
def profile_rows(rows: List[Dict[str, str]], columns: List[str]) -> Dict[str, Any]:
    """결측·중복·분포. **판정하지 않고 세기만 한다** — 판정은 다음 단계다."""
    total = len(rows)
    missing = {c: sum(1 for r in rows if str(r.get(c, "")).strip() == "") for c in columns}
    seen: Dict[Tuple, int] = {}
    for r in rows:
        key = tuple(str(r.get(c, "")) for c in columns)
        seen[key] = seen.get(key, 0) + 1
    duplicates = sum(n - 1 for n in seen.values() if n > 1)
    distinct = {c: len({str(r.get(c, "")) for r in rows}) for c in columns}
    return {"row_count": total, "missing": missing, "duplicate_rows": duplicates,
            "distinct": distinct}


def profile(store: Any, snapshot_id: str, rows: List[Dict[str, str]],
            columns: List[str]) -> Dict[str, Any]:
    return store.advance_snapshot(snapshot_id, m.PROFILED,
                                  profile=profile_rows(rows, columns))


# ── 표준화 ───────────────────────────────────────────────────────────────
def standardize(store: Any, snapshot_id: str, rows: List[Dict[str, str]], *,
                code_columns: Optional[Dict[str, List[str]]] = None,
                unit_columns: Optional[Dict[str, str]] = None,
                expected_units: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """코드·단위를 본다. **미매핑 행과 단위 오류는 격리한다.**

    ⚠️ 매핑되지 않은 코드를 그대로 통과시키면 집계에서 조용히 다른 것과 묶이거나
      빠진다 — 어느 쪽이든 합계는 그럴듯해 보인다.
    ⚠️ 단위가 다른 값을 그대로 더하면 «톤 + 킬로그램» 이 된다. 그 숫자는 틀린 줄도
      모르고 보고서에 실린다."""
    unmapped: List[Dict[str, Any]] = []
    bad_units: List[Dict[str, Any]] = []

    for idx, r in enumerate(rows):
        for col, allowed in (code_columns or {}).items():
            value = str(r.get(col, "")).strip()
            if value and allowed and value not in allowed:
                unmapped.append({"row": idx, "column": col, "value": value})
        for col, want in (expected_units or {}).items():
            got = str((unit_columns or {}).get(col, "")).strip()
            if want and got and got != want:
                bad_units.append({"row": idx, "column": col, "expected": want, "got": got})

    if unmapped or bad_units:
        return store.advance_snapshot(
            snapshot_id, m.QUARANTINED,
            quarantine={"kind": m.QUARANTINE_QUALITY,
                        "reason": "미매핑 코드 또는 단위 불일치",
                        "unmapped": unmapped[:50], "unmapped_count": len(unmapped),
                        "unit_errors": bad_units[:50], "unit_error_count": len(bad_units)})
    return store.advance_snapshot(snapshot_id, m.STANDARDIZED)


# ── 대사 ─────────────────────────────────────────────────────────────────
def reconcile_totals(rows: List[Dict[str, str]],
                     control: Dict[str, Any]) -> Dict[str, Any]:
    """원천이 말한 합계와 **우리가 센 합계**를 맞춘다.

    ★★★ 이것이 「잘린 파일을 전체로 저장하지 않는다」의 실체다 — 읽다 끊긴 파일은
      행 수와 합계가 모자라고, 그 차이가 여기서 드러난다."""
    out: Dict[str, Any] = {"checked": [], "mismatches": []}
    if "row_count" in (control or {}):
        want = int(control["row_count"])
        got = len(rows)
        out["checked"].append({"kind": "row_count", "expected": want, "actual": got})
        if want != got:
            out["mismatches"].append(
                {"kind": "row_count", "expected": want, "actual": got,
                 "note": "행 수가 다릅니다 — 파일이 잘렸거나 다른 판본입니다."})
    for col, want in (control.get("sums") or {}).items():
        got = 0.0
        unreadable = 0
        for r in rows:
            raw = str(r.get(col, "")).strip()
            if not raw:
                continue
            try:
                got += float(raw)
            except ValueError:
                unreadable += 1
        entry = {"kind": "sum", "column": col, "expected": float(want),
                 "actual": round(got, 6), "unreadable": unreadable}
        out["checked"].append(entry)
        #: ⚠️ 부동소수 비교에 **절대 오차**를 쓴다. 상대 오차로 두면 금액이 커질수록
        #:   허용 폭이 커지고, 큰 숫자일수록 틀려도 통과한다 — 반대로 가야 한다.
        if abs(float(want) - got) > 1e-6 or unreadable:
            out["mismatches"].append({**entry,
                                      "note": "합계가 다릅니다 — 잘렸거나 값이 변형됐습니다."})
    out["ok"] = not out["mismatches"]
    return out


def reconcile(store: Any, snapshot_id: str, rows: List[Dict[str, str]],
              control: Dict[str, Any]) -> Dict[str, Any]:
    result = reconcile_totals(rows, control or {})
    if not result["ok"]:
        return store.advance_snapshot(
            snapshot_id, m.QUARANTINED,
            control_total=result,
            quarantine={"kind": m.QUARANTINE_RECONCILIATION,
                        "reason": "원천 합계 대사 불일치",
                        "mismatches": result["mismatches"]})
    return store.advance_snapshot(snapshot_id, m.RECONCILED, control_total=result)


# ── 인증 ─────────────────────────────────────────────────────────────────
def certify_demo(store: Any, snapshot_id: str, certified_by: str = "") -> Dict[str, Any]:
    """시연 인증. **`CERTIFIED ACTUAL` 이 아니다.**

    ⚠️ 실제 Data Owner 가 없는 상태에서 실적 인증을 주장하면, 그 숫자를 본 사람은
      검증된 값이라고 믿는다. 그래서 상태 이름 자체가 `DEMO_CERTIFIED` 다.
    ⚠️ `REAL` 데이터에는 이 인증을 붙이지 않는다 — 붙이는 순간 두 성격이 섞이고,
      섞인 뒤에는 어느 것이 시연이었는지 가릴 수 없다."""
    row = store.get_snapshot(snapshot_id)
    if row is None:
        raise m.DataPreparationError(f"존재하지 않는 Snapshot 입니다: {snapshot_id}")
    if str(row.get("data_kind")) != m.DATA_KIND_DEMO:
        raise m.StateConflict(
            f"«{row.get('data_kind')}» 데이터에는 시연 인증을 붙이지 않습니다 — "
            f"시연 자료와 실제 실적이 섞이면 어느 것이 시연이었는지 가릴 수 없습니다.")
    from core.data_preparation import usage_policy
    usage_policy.require_usable(store, row)
    #: ★★★ [2026-08-20 §7 3단계] **색인을 먼저 계산하고 그다음에 인증한다.**
    #:
    #: ⚠️⚠️ 순서가 중요하다. 인증부터 하면 「인증은 됐는데 색인이 없는 판」이 생길 수
    #:   있고, 그 판의 객체는 Resolver 에게 `UNBOUND` 로 보인다 — 승인된 관계의 끝점에서
    #:   **무결성 장애**가 되어 사고가 **질의 시점**에 터진다. 그때는 고칠 사람이 그
    #:   자리에 없다.
    #: ★ 계약키가 색인 대상이 아니면 빈 목록이고 그것은 정상이다(MVP 대상은 다섯뿐).
    from core.data_preparation import scope_index

    payload = scope_index.plan(row)              # ← 여기서 막히면 인증이 서지 않는다

    #: ★★★ [2026-08-21 P1] 상태 전환과 색인 적재를 **한 트랜잭션**에서 커밋한다.
    #: ⚠️⚠️ 종전에는 인증을 먼저 커밋하고 색인을 따로 썼다. 그 사이가 아무리 짧아도
    #:   「인증됐는데 색인이 없는」 구간이고, 그때 읽은 쪽은 승인된 관계의 끝점에서
    #:   503 을 만난다 — 아무도 아무것도 잘못하지 않았는데.
    def _index(conn, fresh):
        scope_index.write_conn(conn, payload, str(fresh.get("certified_at", "")))

    #: ★ [2026-09-11] 인증자를 남긴다. 시연 인증도 «누가 통과시켰나» 가 필요하다 —
    #:   기본값은 시연 셋업 행위자다(가상회사 자료이므로 `.invalid` 합성 계정).
    return store.advance_snapshot(snapshot_id, m.DEMO_CERTIFIED, on_commit=_index,
                                  certified_by=(certified_by or "demo.data.owner@afs.invalid"))


def certify_demo_replacement(store: Any, old_snapshot_id: str,
                             new_snapshot_id: str) -> Dict[str, Any]:
    """새 시연판 인증과 기존판 철회를 한 번에 확정한다.

    새 판은 프로파일·표준화·대사를 모두 마친 ``RECONCILED`` 상태여야 한다. 색인도
    같은 트랜잭션에서 적재되므로 인증된 판인데 객체 색인이 없는 순간이 생기지 않는다.
    """
    new = store.get_snapshot(new_snapshot_id)
    if new is None:
        raise m.DataPreparationError(f"존재하지 않는 Snapshot 입니다: {new_snapshot_id}")
    from core.data_preparation import usage_policy
    usage_policy.require_usable(store, new)
    from core.data_preparation import scope_index
    payload = scope_index.plan(new)

    def _index(conn, fresh):
        scope_index.write_conn(conn, payload, str(fresh.get("certified_at", "")))

    return store.replace_demo_snapshot(old_snapshot_id, new_snapshot_id,
                                       on_commit=_index)


def display_label(snapshot: Dict[str, Any]) -> str:
    """화면·API·보고서에 붙일 **성격 표시**. 비어 있지 않다.

    ★ 「샘플입니다」를 화면이 말하지 않으면, 그 숫자는 실적으로 읽힌다."""
    kind = str((snapshot or {}).get("data_kind", ""))
    state = str((snapshot or {}).get("state", ""))
    if kind == m.DATA_KIND_DEMO:
        base = "시연용 합성 데이터(DEMO/SYNTHETIC)"
    elif kind == m.DATA_KIND_REAL:
        base = "실제 업무 데이터"
    else:
        base = f"성격 미상({kind or '없음'})"
    if state == m.DEMO_CERTIFIED:
        return base + " · 시연 인증됨 — 실적 인증이 아닙니다"
    if state == m.QUARANTINED:
        return base + " · 격리됨 — 쓰지 마십시오"
    return base + f" · {state or '상태 미상'}"


def _declared_control(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """원 판이 대사에 쓴 **원천 선언 합계**(행 수·열 합계)를 되살린다. 지어내지 않는다."""
    import json
    try:
        result = json.loads(snapshot.get("control_total_json") or "{}")
    except ValueError as exc:
        raise m.DataPreparationError("원 판의 대사 기록을 읽을 수 없습니다.") from exc
    control: Dict[str, Any] = {}
    for entry in result.get("checked") or []:
        if entry.get("kind") == "row_count":
            control["row_count"] = int(entry["expected"])
        elif entry.get("kind") == "sum":
            control.setdefault("sums", {})[str(entry["column"])] = float(entry["expected"])
    return control


def reissue_for_recertification(store: Any, snapshot_id: str, *, workspace_root: str,
                                created_by: str = "") -> Dict[str, Any]:
    """★ [2026-09-25] **재인증 판** — 인증된 판의 봉인 원문 그대로 새 판을 올리고 같은 원천 합계로 대사한다.

    인증이 끝난 판은 바꾸지 않는다(서명·이력 보존 — 「인증 완료 후 변경은 새 Snapshot」). 관문 이전
    서명이거나 업그레이드로 고정 계약이 바뀌어 운영에 쓸 수 없는 판을, 같은 원문으로 새 판을 만들어
    **현재 고정 계약으로 다시 서명받는** 길이다. 결과는 대사까지 마친 판(`RECONCILED`) 또는 격리 판이다.

    ⚠️ 원문 지문이 수집 때와 다르면 만들지 않는다. 원천 합계는 원 판이 대사에 쓴 값을 그대로 쓴다.
    ⚠️ 결속이 활성이 아니면 만들지 않는다 — 폐지된 원천에 새 판을 올리지 않는다."""
    source = store.get_snapshot(snapshot_id)
    if not source:
        raise m.DataPreparationError("판을 찾을 수 없습니다.")
    if source["state"] not in m.CERTIFIED_STATES:
        raise m.StateConflict("인증이 끝난 판만 재인증 판을 만듭니다 — 진행 중인 판은 그대로 서명을 마치십시오.")
    path, checksum = str(source.get("raw_path") or ""), str(source.get("checksum") or "")
    try:
        with open(path, "rb") as stream:
            payload = stream.read()
    except OSError as exc:
        raise m.DataPreparationError("원 판의 봉인 원문을 읽을 수 없습니다.") from exc
    if not path or checksum_bytes(payload) != checksum:
        raise m.StateConflict("원 판의 원문이 수집 때와 다릅니다 — 재인증 판을 만들 수 없습니다.")
    binding = store.get_binding(source["binding_id"])
    if not binding or binding.get("state") != m.ACTIVE:
        raise m.StateConflict("활성 결속의 판만 재인증 판을 만듭니다.")
    control = _declared_control(source)
    name = os.path.basename(path).split("__", 1)[-1] or "recertification.csv"
    fresh = ingest(store, binding=binding, payload=payload, file_name=name, workspace_root=workspace_root,
                   created_by=created_by, data_kind=source["data_kind"])
    parsed = parse_csv(payload, file_name=name)
    row = profile(store, fresh["snapshot_id"], parsed.rows, parsed.columns)
    if row["state"] == m.QUARANTINED:
        return row
    row = standardize(store, fresh["snapshot_id"], parsed.rows)
    if row["state"] == m.QUARANTINED:
        return row
    return reconcile(store, fresh["snapshot_id"], parsed.rows, control)


def run_pipeline(store: Any, snapshot_id: str, rows: List[Dict[str, str]],
                 columns: List[str], *, control: Optional[Dict[str, Any]] = None,
                 code_columns: Optional[Dict[str, List[str]]] = None,
                 expected_units: Optional[Dict[str, str]] = None,
                 unit_columns: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """`RAW` → … → `DEMO_CERTIFIED`. **어느 단계에서 격리되면 거기서 멈춘다.**"""
    row = profile(store, snapshot_id, rows, columns)
    if row["state"] == m.QUARANTINED:
        return row
    row = standardize(store, snapshot_id, rows, code_columns=code_columns,
                      unit_columns=unit_columns, expected_units=expected_units)
    if row["state"] == m.QUARANTINED:
        return row
    row = reconcile(store, snapshot_id, rows, control or {})
    if row["state"] == m.QUARANTINED:
        return row
    return certify_demo(store, snapshot_id)


# ── [M0 · 2026-09-12] 회사 실적 인증 — 서명은 «종류» 이고 병렬이다 ──────────
#
# ## 왜 `certify_demo` 처럼 한 함수로 안 되나
#
# 시연·공표 자료는 **서명이 하나**다. 회사 실적은 용도에 따라 **둘일 수 있다**
# (부서 운영용은 소유 부서장만, 전사 경영 보고용은 + 임원). 그래서 「서명한다」와
# 「인증이 선다」를 나눈다 — 필요한 종류가 **다 모였을 때** 판이 인증된다.
#
# ★ `publication_reviews` 와 같은 모양이다. 새 어휘를 만들지 않는다.
#
# ## ⚠️ 순차가 아니라 병렬이다
#
# 순차 결재로 만들면 부서장이 휴가 갈 때 **전체가 멈추고**, 결재선이 조직 개편마다
# 코드 변경이 된다. 필요한 «종류» 만 정하고 순서는 사람에게 맡긴다.


def _owner_dept(store: Any, snapshot: Mapping[str, Any]) -> str:
    """이 판의 **소유 부서를 «찾는다»**. 받지 않는다.

    ★★★ 인증자를 인자로 그냥 받으면 아무 이름이나 들어간다. `SOURCE_CERTIFIED` 가
      「원천이 승인됐는가」를 등록부에 «물어본» 것과 같은 모양이어야 한다.

    ⚠️ 결속이 없으면 `UNBOUND` 로 **인증이 서지 않는다.** 「누구 데이터인지 모르는
      실적」에 서명을 받으면 그 서명은 무엇에 대한 서명인지 알 수 없다."""
    from core.data_preparation import ownership_binding as ob

    with store.transaction() as conn:
        binding = ob.resolve(
            conn,
            tenant_id=str(snapshot.get("tenant_id") or ""),
            entity_mode=str(snapshot.get("entity_mode") or ""),
            dataset_contract_key=str(snapshot.get("dataset_contract_key") or ""),
            scope_node_id=str(snapshot.get("scope_node_id") or ""))
    if not binding:
        raise m.DataPreparationError(
            f"이 판의 소유 부서가 결속돼 있지 않습니다"
            f"({snapshot.get('dataset_contract_key')}). 「누구 데이터인지 모르는 실적」에 "
            f"서명을 받으면 그 서명은 무엇에 대한 것인지 알 수 없습니다 — "
            f"먼저 데이터셋 소유권을 승인하십시오.")
    return str(binding.get("owner_dept_id") or "")


def sign_actual_certification(store: Any, snapshot_id: str, *, review_kind: str,
                              actor: str, reconciliation_evidence: str, use_kind: str,
                              period_from: str = "", period_to: str = "",
                              context: Dict[str, Any] = None, subject_id: str = "",
                              expected_subject_digest: str = "", client_request_id: str = "") -> Dict[str, Any]:
    """회사별 서명권·불변 대상·멱등을 단일 DP 쓰기 transaction에서 검사한다."""
    from core.data_preparation.certification_subject import sign
    return sign(store, snapshot_id, review_kind=review_kind, actor=actor, context=context or {},
                reconciliation_evidence=reconciliation_evidence, use_kind=use_kind,
                period_from=period_from, period_to=period_to, subject_id=subject_id,
                expected_subject_digest=expected_subject_digest, client_request_id=client_request_id)


def actual_certifications(store: Any, snapshot_id: str) -> List[Dict[str, Any]]:
    """내부 감사 조회. HTTP는 권한과 snapshot을 함께 읽는 certification_subject.read 사용."""
    with store.transaction() as conn:
        conn.execute("BEGIN")
        return [dict(r) for r in conn.execute(
            "SELECT s.* FROM certification_signatures s JOIN certification_subject_heads h "
            "ON s.subject_id=h.subject_id WHERE h.snapshot_id=? ORDER BY s.review_kind", (snapshot_id,))]
