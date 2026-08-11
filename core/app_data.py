"""[트랙 I-1] 생성 앱 데이터 평면 — 도메인 로직(스키마 검증 · 데이터셋 · 레코드).

설계: `docs/design_app_data_plane_2026-08-08.md`

## 이 파일의 책임과 책임 아닌 것

| | |
|---|---|
| **한다** | 스키마 선언 검증 · payload 검증 · 데이터셋/레코드 CRUD · 논리 삭제 |
| **하지 않는다** | **권한 판정**(라우트가 `api/deps.py` 로 한다) · 감사 기록(라우트) |

⚠️ 권한을 여기서도 보고 라우트에서도 보면 **같은 판정이 두 곳에 생긴다.** 이 저장소가 반복해
  겪은 결함 유형이다(어긋나면 조용히 틀린 답을 준다). 판정은 라우트 한 곳에만 둔다.
  대신 이 파일은 **호출자가 주체를 넘기지 않으면 거부**한다 — 「누가 썼는지 모르는 레코드」를
  만들 수 없게 하는 것은 검증이지 권한 판정이 아니다.

LLM 0콜.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.app_data_store import AppDataStore, app_data_store

# ── 한계값 ────────────────────────────────────────────────────────────────
# ⚠️ 이 값들은 **추정**이다. 설계서 §9-3(목표 규모 확정)이 미결이므로 «안전한 쪽»으로 잡았다.
#   규모가 확정되면 재조정한다 — 지금 근거 없는 큰 값을 넣으면 첫 사고가 운영에서 난다.
MAX_FIELDS = 60
MAX_NAME_LEN = 64
MAX_STRING_LEN = 4_000
MAX_TEXT_LEN = 100_000
#: ★★ **단일 필드의 최대값이 이 안에 들어가야 한다.** 초판은 256KB 였는데 한글은 UTF-8 로
#:   3바이트라 `MAX_TEXT_LEN`(100,000자) 하나가 약 300KB 다 — 즉 **스키마가 허용하는 값을
#:   저장할 수 없는 구간**이 생겼다(테스트에서 잡혔다).
#:   사용자에게는 「길이 제한 안인데 크기 초과로 거부됨」으로 보이고, 그 둘의 관계는 화면
#:   어디에도 없다. 두 한계는 **서로 정합해야** 하며, 그 관계를 아래 식으로 못박는다.
MAX_PAYLOAD_BYTES = 512 * 1024
assert MAX_TEXT_LEN * 3 <= MAX_PAYLOAD_BYTES, (
    "text 필드 하나의 최대값(한글 3바이트 기준)이 레코드 총량 한계를 넘습니다 — "
    "선언상 허용된 값을 저장할 수 없게 됩니다.")
MAX_RECORDS_PER_DATASET = 100_000
MAX_DATASETS_PER_RELEASE = 40

FIELD_TYPES = ("string", "text", "number", "boolean", "date")

#: 필드 이름으로 쓸 수 없는 것 — 레코드 봉투(envelope)의 예약어.
#: 앱이 `created_by` 를 자기 필드로 쓰면 화면에서 «누가 만들었나» 가 두 개가 되고,
#: 그중 하나는 앱이 자유롭게 쓸 수 있는 값이다 — 감사 표시가 위조 가능해진다.
RESERVED_FIELD_NAMES = frozenset({
    "record_id", "dataset_id", "created_by", "created_at",
    "updated_by", "updated_at", "deleted_by", "deleted_at",
})


class AppDataError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── 스키마 ────────────────────────────────────────────────────────────────
def normalize_schema(raw: Any) -> Dict[str, Any]:
    """앱이 선언한 스키마를 검증하고 정규화한다.

    입력 형태: `{"fields": [{"name":..., "type":..., "required":..., "label":...}, ...]}`
    ⚠️ 리스트만 준 경우도 받는다 — 생성기가 `fields` 봉투를 빠뜨리는 것은 흔하고, 그때
      «스키마가 비었다» 로 처리하면 **모든 필드가 거부되는 앱**이 조용히 만들어진다.
    """
    if isinstance(raw, list):
        raw = {"fields": raw}
    if not isinstance(raw, dict):
        raise AppDataError("schema 는 객체여야 합니다.")
    fields_raw = raw.get("fields")
    if not isinstance(fields_raw, list) or not fields_raw:
        raise AppDataError("schema.fields 는 비어 있지 않은 배열이어야 합니다 — "
                           "필드 선언이 없으면 어떤 값도 저장할 수 없습니다.")
    if len(fields_raw) > MAX_FIELDS:
        raise AppDataError(f"필드는 최대 {MAX_FIELDS}개입니다(선언 {len(fields_raw)}개).")

    seen: set = set()
    fields: List[Dict[str, Any]] = []
    for i, f in enumerate(fields_raw):
        if not isinstance(f, dict):
            raise AppDataError(f"fields[{i}] 는 객체여야 합니다.")
        name = str(f.get("name", "")).strip()
        if not name:
            raise AppDataError(f"fields[{i}].name 은 필수입니다.")
        if len(name) > MAX_NAME_LEN:
            raise AppDataError(f"필드 이름이 너무 깁니다({name[:20]}…).")
        if name in RESERVED_FIELD_NAMES:
            raise AppDataError(
                f"'{name}' 은 예약된 이름이라 필드로 쓸 수 없습니다 — 레코드가 이미 갖는 "
                f"항목이며, 앱이 같은 이름을 쓰면 «누가 언제 만들었나» 를 앱이 덮어쓸 수 "
                f"있게 됩니다(감사 표시 위조).")
        if name in seen:
            raise AppDataError(f"필드 이름이 중복됩니다: {name}")
        seen.add(name)

        ftype = str(f.get("type", "string")).strip().lower() or "string"
        if ftype not in FIELD_TYPES:
            raise AppDataError(f"'{name}' 의 type 은 {FIELD_TYPES} 중 하나여야 합니다: {ftype}")

        fields.append({
            "name": name,
            "type": ftype,
            "required": bool(f.get("required", False)),
            "label": str(f.get("label", "") or name).strip(),
        })
    return {"fields": fields}


def _coerce(name: str, ftype: str, value: Any) -> Any:
    """타입 검증. **조용히 고치지 않고 거부한다.**

    ⚠️ 「문자열 "3" 을 숫자 3 으로 받아 준다」 같은 관용은 편해 보이지만, 그 순간 저장된 값의
      타입이 입력 경로마다 달라진다. 나중에 합계를 내면 어떤 행은 더해지고 어떤 행은 이어붙는다.
    """
    if value is None:
        return None
    if ftype in ("string", "text"):
        if not isinstance(value, str):
            raise AppDataError(f"'{name}' 은 문자열이어야 합니다(받은 값: {type(value).__name__}).")
        cap = MAX_TEXT_LEN if ftype == "text" else MAX_STRING_LEN
        if len(value) > cap:
            raise AppDataError(f"'{name}' 이 최대 길이({cap}자)를 넘었습니다.")
        return value
    if ftype == "number":
        # ⚠️ 파이썬에서 bool 은 int 의 하위형이다 — 먼저 걸러내지 않으면 True 가 1 로 저장된다.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppDataError(f"'{name}' 은 숫자여야 합니다(받은 값: {type(value).__name__}).")
        return value
    if ftype == "boolean":
        if not isinstance(value, bool):
            raise AppDataError(f"'{name}' 은 true/false 여야 합니다.")
        return value
    if ftype == "date":
        if not isinstance(value, str):
            raise AppDataError(f"'{name}' 은 날짜 문자열이어야 합니다.")
        v = value.strip()
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            raise AppDataError(f"'{name}' 은 ISO 날짜 형식이어야 합니다(예: 2026-08-08): {v[:30]}")
        return v
    raise AppDataError(f"'{name}' 의 타입을 해석할 수 없습니다: {ftype}")


def validate_payload(schema: Dict[str, Any], payload: Any, *, partial: bool = False) -> Dict[str, Any]:
    """레코드 값을 스키마에 맞춰 검증한다.

    `partial=True` 는 수정용 — 준 필드만 본다(안 준 필드는 기존 값 유지).
    ★ **선언에 없는 키는 거부한다.** 「그냥 넣는다」로 두면 스키마가 의미를 잃고,
      I-5 카탈로그 등재가 «이 앱은 이런 필드를 갖는다» 고 거짓을 말하게 된다.
    """
    if not isinstance(payload, dict):
        raise AppDataError("레코드 값은 객체여야 합니다.")
    # 계약상 `schema` 는 `normalize_schema()` 를 거친 것이다(저장할 때 정규화한다).
    # ⚠️ 그래도 `required`·`label` 을 `.get()` 으로 읽는다 — 정규화를 거치지 않은 스키마가
    #   들어오면 `KeyError` 가 500 으로 나가고, 그 오류는 **원인을 가리키지 않는다.**
    fields = {f["name"]: f for f in schema.get("fields", []) if f.get("name")}
    unknown = [k for k in payload if k not in fields]
    if unknown:
        raise AppDataError(
            f"선언되지 않은 필드입니다: {', '.join(sorted(unknown)[:8])}"
            f"{' 외' if len(unknown) > 8 else ''} — 데이터셋 스키마에 먼저 추가해야 합니다.")

    out: Dict[str, Any] = {}
    for name, f in fields.items():
        required = bool(f.get("required", False))
        label = f.get("label") or name
        if name not in payload:
            if partial:
                continue
            if required:
                raise AppDataError(f"'{label}'({name}) 은 필수 항목입니다.")
            out[name] = None
            continue
        val = _coerce(name, str(f.get("type", "string") or "string"), payload[name])
        if required and (val is None or (isinstance(val, str) and not val.strip())):
            raise AppDataError(f"'{label}'({name}) 은 필수 항목입니다.")
        out[name] = val

    blob = json.dumps(out, ensure_ascii=False)
    if len(blob.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise AppDataError(f"레코드가 최대 크기({MAX_PAYLOAD_BYTES // 1024}KB)를 넘었습니다.")
    return out


# ── 데이터셋 ──────────────────────────────────────────────────────────────
class AppDataService:
    def __init__(self, store: Optional[AppDataStore] = None):
        self._store = store or app_data_store

    # 데이터셋 ---------------------------------------------------------
    def create_dataset(self, release_id: str, name: str, schema: Any, *,
                       actor_id: str, label: str = "", app_class: str = "",
                       owner_dept_id: str = "", scope_node_id: str = "",
                       tenant_id: str = "tenant_default") -> Dict[str, Any]:
        release_id = (release_id or "").strip()
        name = (name or "").strip()
        actor_id = (actor_id or "").strip()
        if not release_id:
            raise AppDataError("release_id 는 필수입니다.")
        if not name:
            raise AppDataError("데이터셋 이름은 필수입니다.")
        if len(name) > MAX_NAME_LEN:
            raise AppDataError("데이터셋 이름이 너무 깁니다.")
        if not actor_id:
            # 권한 판정이 아니라 **귀속 검증**이다 — 누가 만들었는지 모르는 데이터셋은
            # 나중에 「이 데이터는 누구 책임인가」에 답할 수 없다.
            raise AppDataError("데이터셋 생성에는 주체(actor_id)가 필요합니다.")

        norm = normalize_schema(schema)
        exists = self._store.one(
            "SELECT dataset_id FROM app_datasets WHERE release_id=? AND name=?",
            (release_id, name))
        if exists:
            raise AppDataError(f"같은 이름의 데이터셋이 이미 있습니다: {name}")
        n = self._store.scalar(
            "SELECT COUNT(*) FROM app_datasets WHERE release_id=? AND retired_at=''",
            (release_id,)) or 0
        if n >= MAX_DATASETS_PER_RELEASE:
            raise AppDataError(f"앱당 데이터셋은 최대 {MAX_DATASETS_PER_RELEASE}개입니다.")

        did = _nid("ds")
        ts = _now()
        self._store.execute(
            "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, label, "
            "schema_json, app_class, owner_dept_id, scope_node_id, created_by, created_at, "
            "updated_at, retired_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'')",
            (did, tenant_id, release_id, name, (label or name).strip(),
             json.dumps(norm, ensure_ascii=False), app_class, owner_dept_id, scope_node_id,
             actor_id, ts, ts))
        return self.get_dataset(did)  # type: ignore[return-value]

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.one("SELECT * FROM app_datasets WHERE dataset_id=?", (dataset_id,))
        return self._dataset_view(row) if row else None

    def find_dataset(self, release_id: str, name: str) -> Optional[Dict[str, Any]]:
        """★ 앱은 **이름으로만** 데이터셋을 부른다(설계 §7 규칙 4).

        `release_id` 는 호스트가 붙인다 — 앱이 자기 릴리스를 말하게 하면 남의 앱 데이터를
        요청할 수 있다."""
        row = self._store.one(
            "SELECT * FROM app_datasets WHERE release_id=? AND name=?",
            ((release_id or "").strip(), (name or "").strip()))
        return self._dataset_view(row) if row else None

    def list_datasets(self, release_id: str = "", include_retired: bool = False
                      ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM app_datasets WHERE 1=1"
        params: List[Any] = []
        if release_id:
            sql += " AND release_id=?"
            params.append(release_id.strip())
        if not include_retired:
            sql += " AND retired_at=''"
        sql += " ORDER BY created_at DESC"
        return [self._dataset_view(r) for r in self._store.query(sql, tuple(params))]

    def update_schema(self, dataset_id: str, schema: Any, *, actor_id: str) -> Dict[str, Any]:
        """스키마를 바꾼다.

        ⚠️ **필드 제거는 기존 레코드의 값을 화면에서 사라지게 한다**(데이터는 payload 에 남지만
          선언에 없으므로 조회 결과에서 빠진다). 조용히 지우지 않고, 제거되는 필드를 응답으로
          알려 호출자가 판단하게 한다."""
        ds = self.get_dataset(dataset_id)
        if not ds:
            raise AppDataError("데이터셋을 찾을 수 없습니다.")
        if not (actor_id or "").strip():
            raise AppDataError("스키마 변경에는 주체(actor_id)가 필요합니다.")
        norm = normalize_schema(schema)
        before = {f["name"] for f in ds["schema"]["fields"]}
        after = {f["name"] for f in norm["fields"]}
        self._store.execute(
            "UPDATE app_datasets SET schema_json=?, updated_at=? WHERE dataset_id=?",
            (json.dumps(norm, ensure_ascii=False), _now(), dataset_id))
        out = self.get_dataset(dataset_id)
        out["removed_fields"] = sorted(before - after)  # type: ignore[index]
        out["added_fields"] = sorted(after - before)    # type: ignore[index]
        return out  # type: ignore[return-value]

    def retire_dataset(self, dataset_id: str, *, actor_id: str) -> Dict[str, Any]:
        """데이터셋을 폐지한다. **레코드는 지우지 않는다**(설계 §9-2 권장 ⓐ).

        ⚠️ 물리 삭제하면 감사 원장이 가리키는 대상이 사라진다."""
        ds = self.get_dataset(dataset_id)
        if not ds:
            raise AppDataError("데이터셋을 찾을 수 없습니다.")
        if not (actor_id or "").strip():
            raise AppDataError("폐지에는 주체(actor_id)가 필요합니다.")
        if ds["retired_at"]:
            return ds
        self._store.execute(
            "UPDATE app_datasets SET retired_at=?, updated_at=? WHERE dataset_id=?",
            (_now(), _now(), dataset_id))
        return self.get_dataset(dataset_id)  # type: ignore[return-value]

    # 레코드 -----------------------------------------------------------
    def create_record(self, dataset_id: str, payload: Any, *, actor_id: str) -> Dict[str, Any]:
        ds = self._require_active(dataset_id)
        if not (actor_id or "").strip():
            raise AppDataError("레코드 생성에는 주체(actor_id)가 필요합니다.")
        clean = validate_payload(ds["schema"], payload)
        n = self._store.scalar(
            "SELECT COUNT(*) FROM app_records WHERE dataset_id=? AND deleted_at=''",
            (dataset_id,)) or 0
        if n >= MAX_RECORDS_PER_DATASET:
            raise AppDataError(
                f"데이터셋당 레코드는 최대 {MAX_RECORDS_PER_DATASET:,}건입니다. "
                f"한도에 도달했습니다 — 보관 정책이 필요합니다.")
        rid = _nid("rec")
        ts = _now()
        self._store.execute(
            "INSERT INTO app_records (record_id, dataset_id, payload_json, created_by, "
            "created_at, updated_by, updated_at, deleted_by, deleted_at) "
            "VALUES (?,?,?,?,?,'','','','')",
            (rid, dataset_id, json.dumps(clean, ensure_ascii=False), actor_id.strip(), ts))
        return self.get_record(rid)  # type: ignore[return-value]

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.one("SELECT * FROM app_records WHERE record_id=?", (record_id,))
        return self._record_view(row) if row else None

    def list_records(self, dataset_id: str, *, limit: int = 200, offset: int = 0,
                     include_deleted: bool = False, created_by: str = "",
                     ) -> Tuple[List[Dict[str, Any]], int]:
        """레코드 목록과 **전체 건수**를 함께 돌려준다.

        ★ 건수를 함께 주는 이유: 화면이 `len(rows)` 로 «전부» 를 표시하면 200건 상한에 걸린
          순간 사용자는 «우리 데이터는 200건» 으로 읽는다. 목록과 총계는 다른 값이다."""
        limit = max(1, min(int(limit or 200), 500))
        offset = max(0, int(offset or 0))
        where = "WHERE dataset_id=?"
        params: List[Any] = [dataset_id]
        if not include_deleted:
            where += " AND deleted_at=''"
        if created_by:
            where += " AND created_by=?"
            params.append(created_by)
        total = self._store.scalar(
            f"SELECT COUNT(*) FROM app_records {where}", tuple(params)) or 0
        rows = self._store.query(
            f"SELECT * FROM app_records {where} ORDER BY created_at DESC, record_id "
            f"LIMIT ? OFFSET ?", tuple(params) + (limit, offset))
        return [self._record_view(r) for r in rows], int(total)

    def update_record(self, record_id: str, payload: Any, *, actor_id: str) -> Dict[str, Any]:
        row = self._store.one("SELECT * FROM app_records WHERE record_id=?", (record_id,))
        if not row:
            raise AppDataError("레코드를 찾을 수 없습니다.")
        if row["deleted_at"]:
            raise AppDataError("삭제된 레코드는 수정할 수 없습니다.")
        if not (actor_id or "").strip():
            raise AppDataError("레코드 수정에는 주체(actor_id)가 필요합니다.")
        ds = self._require_active(row["dataset_id"])
        current = json.loads(row["payload_json"] or "{}")
        patch = validate_payload(ds["schema"], payload, partial=True)
        current.update(patch)
        # 부분 수정이어도 **필수 항목이 비면 안 된다** — 부분 경로로 필수를 우회할 수 있으면
        # 그 제약은 없는 것과 같다.
        merged = validate_payload(ds["schema"], current)
        self._store.execute(
            "UPDATE app_records SET payload_json=?, updated_by=?, updated_at=? "
            "WHERE record_id=?",
            (json.dumps(merged, ensure_ascii=False), actor_id.strip(), _now(), record_id))
        return self.get_record(record_id)  # type: ignore[return-value]

    def delete_record(self, record_id: str, *, actor_id: str) -> Dict[str, Any]:
        """★ 논리 삭제. 물리 삭제는 제공하지 않는다(설계 §4-2)."""
        row = self._store.one("SELECT * FROM app_records WHERE record_id=?", (record_id,))
        if not row:
            raise AppDataError("레코드를 찾을 수 없습니다.")
        if not (actor_id or "").strip():
            raise AppDataError("레코드 삭제에는 주체(actor_id)가 필요합니다.")
        if row["deleted_at"]:
            return self.get_record(record_id)  # type: ignore[return-value]
        self._store.execute(
            "UPDATE app_records SET deleted_by=?, deleted_at=? WHERE record_id=?",
            (actor_id.strip(), _now(), record_id))
        return self.get_record(record_id)  # type: ignore[return-value]

    def count_records(self, dataset_id: str) -> int:
        return int(self._store.scalar(
            "SELECT COUNT(*) FROM app_records WHERE dataset_id=? AND deleted_at=''",
            (dataset_id,)) or 0)

    # 내부 -------------------------------------------------------------
    def _require_active(self, dataset_id: str) -> Dict[str, Any]:
        ds = self.get_dataset(dataset_id)
        if not ds:
            raise AppDataError("데이터셋을 찾을 수 없습니다.")
        if ds["retired_at"]:
            raise AppDataError("폐지된 데이터셋에는 쓸 수 없습니다.")
        return ds

    @staticmethod
    def _dataset_view(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        try:
            out["schema"] = json.loads(out.pop("schema_json", "") or "{}")
        except Exception:
            # 스키마를 못 읽으면 **빈 것으로 두지 않는다** — 빈 스키마는 «필드가 없는 앱» 으로
            # 읽히고, 그 상태에서 쓰기를 시도하면 전부 「선언되지 않은 필드」로 거부된다.
            # 원인이 파싱 실패라는 것을 드러낸다.
            out["schema"] = {"fields": [], "unreadable": True}
        return out

    @staticmethod
    def _record_view(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        try:
            out["payload"] = json.loads(out.pop("payload_json", "") or "{}")
        except Exception:
            out["payload"] = {}
            out["unreadable"] = True
        out["deleted"] = bool(out.get("deleted_at"))
        return out


app_data_service = AppDataService()
