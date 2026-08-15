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

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


#: 계약이 데이터셋에 줄 수 있는 행동. **닫힌 목록**이다.
#: ⚠️ `core.app_runtime_contract.ACTIONS` 와 같은 값이어야 한다 — 두 목록이 갈라지면
#:   계약이 허용한 행동을 런타임이 모르거나, 런타임이 계약에 없는 행동을 허용한다.
#:   그 모듈을 import 하지 않는 이유는 순환 참조다(계약이 데이터 평면 상한을 읽는다).
#:   대신 `tests/test_app_dataset_binding.py` 가 두 목록의 동일성을 잠근다.
DATASET_ACTIONS: Tuple[str, ...] = ("read", "create", "update", "delete")


class AppDataError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


def normalize_actions(actions: Any) -> Tuple[str, ...]:
    """행동 목록을 **선언 순서가 아니라 고정 순서**로 정규화한다.

    ⚠️ 순서를 보존하면 같은 권한이 다른 문자열로 저장되고, 「바뀌었나」 비교가 거짓이 된다.
    ⚠️⚠️ 모르는 행동은 **버리지 않고 던진다** — 조용히 버리면 계약이 `purge` 를 선언해도
      아무 일도 일어나지 않고, 아무도 그 선언이 무시된 줄 모른다."""
    if actions is None:
        return ()
    if isinstance(actions, str):
        raise AppDataError("allowed_actions 는 목록이어야 합니다(문자열 하나가 아니라).")
    got = {str(a).strip() for a in actions if str(a).strip()}
    unknown = sorted(got - set(DATASET_ACTIONS))
    if unknown:
        raise AppDataError(f"알 수 없는 행동입니다: {unknown} — "
                           f"가능한 것은 {list(DATASET_ACTIONS)} 입니다.")
    return tuple(a for a in DATASET_ACTIONS if a in got)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _load_schema(raw: Any) -> Dict[str, Any]:
    """저장된 스키마를 읽는다.

    ⚠️ 못 읽으면 **빈 것으로 두지 않는다** — 빈 스키마는 «필드가 없는 앱» 으로 읽히고,
      그 상태에서 쓰기를 시도하면 전부 「선언되지 않은 필드」로 거부된다. 원인이 파싱
      실패라는 것을 드러낸다."""
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {"fields": [], "unreadable": True}


def schema_fingerprint(schema: Any) -> str:
    """정규화된 스키마의 지문(sha256 앞 16자).

    ★ 계약 판이 **바뀌지 않았음**을 증명하는 값이다. 키 순서에 흔들리면 같은 내용이 다른
      지문을 갖고, 그러면 「판이 바뀌었다」는 판정이 거짓이 되어 아무도 믿지 않게 된다."""
    norm = normalize_schema(schema)
    body = json.dumps(norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


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
                       tenant_id: str = "tenant_default",
                       app_id: str = "", dataset_key: str = "",
                       allowed_actions: Optional[Sequence[str]] = None,
                       contract_revision: int = 0) -> Dict[str, Any]:
        """데이터셋을 만들고 **이 릴리스에 결속**한다.

        ★ `allowed_actions` 를 주면 계약 결속(`contract_bound=1`)이 되고, 런타임 2차 판정이
          그 목록으로 행동을 자른다. 주지 않으면 계약 이전(레거시) 결속이다 —
          ⚠️ 「모르면 전부 허용」이 아니라 **「계약이 말한 적 없음」**이라고 기록한다.
          그 둘을 같은 모양으로 두면 나중에 어느 쪽이었는지 아무도 모른다."""
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
        app_id = (app_id or "").strip()
        dataset_key = (dataset_key or name).strip()
        did = _nid("ds")
        ts = _now()

        #: ★★★ 생성·판·결속·허용행동을 **하나의 트랜잭션**으로. 나뉘면 결속에 실패했을 때
        #:   아무 릴리스도 가리키지 않는 **고아 데이터셋**이 남고, 그것은 이름으로 찾히지
        #:   않으므로 다음 요청이 **또 만든다.**
        with self._store.transaction() as conn:
            if self._store.row(conn,
                               "SELECT 1 FROM app_release_dataset_bindings "
                               " WHERE release_id=? AND runtime_name=?", (release_id, name)):
                raise AppDataError(f"같은 이름의 데이터셋이 이미 있습니다: {name}")
            n = len(self._store.rows(
                conn,
                "SELECT 1 FROM app_release_dataset_bindings b "
                "  JOIN app_datasets d ON d.dataset_id = b.dataset_id "
                " WHERE b.release_id=? AND d.retired_at=''", (release_id,)))
            if n >= MAX_DATASETS_PER_RELEASE:
                raise AppDataError(f"앱당 데이터셋은 최대 {MAX_DATASETS_PER_RELEASE}개입니다.")
            conn.execute(
                "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, label, "
                "schema_json, app_class, owner_dept_id, scope_node_id, created_by, created_at, "
                "updated_at, retired_at, app_id, dataset_key) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'',?,?)",
                (did, tenant_id, release_id, name, (label or name).strip(),
                 json.dumps(norm, ensure_ascii=False), app_class, owner_dept_id, scope_node_id,
                 actor_id, ts, ts, app_id, dataset_key))
            self._bind_in_tx(conn, release_id, did, runtime_name=name,
                             allowed_actions=allowed_actions, schema=norm,
                             contract_revision=contract_revision)
        return self.get_dataset(did)  # type: ignore[return-value]

    # 릴리스 결속 ------------------------------------------------------
    def bind_release(self, release_id: str, dataset_id: str, *,
                     allowed_actions: Optional[Sequence[str]] = None,
                     schema: Any = None, contract_revision: int = 0,
                     runtime_name: str = "") -> Dict[str, Any]:
        """이 릴리스가 이 데이터셋의 **어느 판을 어떤 권한으로** 쓰는지 적는다.

        ★ 같은 (릴리스, 데이터셋) 을 다시 결속하면 덮어쓴다 — 계약 개정으로
          `allowed_actions` 가 **줄어들면 즉시 좁아져야** 하기 때문이다. 늘어난 것만
          반영하고 줄어든 것을 무시하면 회수되지 않는 권한이 남는다."""
        release_id = (release_id or "").strip()
        dataset_id = (dataset_id or "").strip()
        if not release_id or not dataset_id:
            raise AppDataError("결속에는 release_id 와 dataset_id 가 필요합니다.")
        with self._store.transaction() as conn:
            self._bind_in_tx(conn, release_id, dataset_id, runtime_name=runtime_name,
                             allowed_actions=allowed_actions, schema=schema,
                             contract_revision=contract_revision)
        return self.binding_for(release_id, dataset_id)  # type: ignore[return-value]

    def _bind_in_tx(self, conn, release_id: str, dataset_id: str, *, runtime_name: str,
                    allowed_actions: Optional[Sequence[str]], schema: Any,
                    contract_revision: int) -> None:
        """결속의 실체. **트랜잭션 안에서만** 부른다."""
        bound = allowed_actions is not None
        acts = normalize_actions(allowed_actions) if bound else ()
        prev = self._store.row(
            conn, "SELECT * FROM app_release_dataset_bindings WHERE release_id=? AND dataset_id=?",
            (release_id, dataset_id))
        if not runtime_name:
            #: 이름은 결속에 봉인된다. 기존 결속이 있으면 그 이름을 지키고, 없으면
            #: 데이터셋 마스터에서 한 번 가져온다.
            runtime_name = str((prev or {}).get("runtime_name") or "")
        if not runtime_name:
            master = self._store.row(
                conn, "SELECT name FROM app_datasets WHERE dataset_id=?", (dataset_id,))
            if not master:
                raise AppDataError("결속할 데이터셋이 없습니다.")
            runtime_name = str(master["name"])

        version_id = str((prev or {}).get("version_id") or "")
        if schema is not None:
            version_id = self._ensure_version_in_tx(conn, dataset_id, schema, contract_revision)

        clash = self._store.row(
            conn, "SELECT dataset_id FROM app_release_dataset_bindings "
                  " WHERE release_id=? AND runtime_name=? AND dataset_id<>?",
            (release_id, runtime_name, dataset_id))
        if clash:
            raise AppDataError(
                f"이 릴리스에는 이미 «{runtime_name}» 이라는 다른 데이터셋이 결속돼 있습니다 "
                f"({clash['dataset_id']}) — 앱은 이름으로만 부르므로 둘이면 답할 수 없습니다.")

        if prev:
            conn.execute(
                "UPDATE app_release_dataset_bindings SET allowed_actions=?, contract_bound=?, "
                "version_id=?, runtime_name=? WHERE release_id=? AND dataset_id=?",
                (",".join(acts), 1 if bound else 0, version_id, runtime_name,
                 release_id, dataset_id))
        else:
            conn.execute(
                "INSERT INTO app_release_dataset_bindings (binding_id, release_id, dataset_id, "
                "version_id, runtime_name, allowed_actions, contract_bound, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (_nid("bind"), release_id, dataset_id, version_id, runtime_name,
                 ",".join(acts), 1 if bound else 0, _now()))

    def _ensure_version_in_tx(self, conn, dataset_id: str, schema: Any,
                              contract_revision: int) -> str:
        """계약 판을 남긴다. **판은 불변이다.**

        ★★★ 같은 `(dataset_id, contract_revision)` 에 **다른 스키마**가 들어오면 거부한다.
          덮어쓰게 두면 **이미 승인된 revision 의 의미가 나중에 바뀐다** — 승인 원장은
          「revision 3 을 승인했다」고 말하는데 revision 3 의 내용은 그 뒤에 달라져 있고,
          3단계에서 봉인할 계약 지문의 역사도 함께 변조된다.

        · 같은 정규화 스키마 → **멱등 성공**(재실행 가능해야 한다)
        · 다른 스키마       → **충돌 거부**. 바꾸려면 새 revision 을 발급한다."""
        norm = normalize_schema(schema)
        fp = schema_fingerprint(norm)
        row = self._store.row(
            conn, "SELECT version_id, schema_fingerprint FROM app_dataset_versions "
                  " WHERE dataset_id=? AND contract_revision=?",
            (dataset_id, int(contract_revision)))
        if row:
            if str(row["schema_fingerprint"] or "") != fp:
                raise AppDataError(
                    f"계약 revision {contract_revision} 의 스키마가 이미 다른 내용으로 "
                    f"확정돼 있습니다(기록 {row['schema_fingerprint'] or '(지문 없음)'} · "
                    f"요청 {fp}) — 승인된 판은 바뀌지 않습니다. 새 revision 을 발급하십시오.")
            return str(row["version_id"])
        vid = _nid("dsv")
        conn.execute(
            "INSERT INTO app_dataset_versions (version_id, dataset_id, contract_revision, "
            "schema_json, schema_fingerprint, created_at) VALUES (?,?,?,?,?,?)",
            (vid, dataset_id, int(contract_revision),
             json.dumps(norm, ensure_ascii=False), fp, _now()))
        return vid

    def binding_for(self, release_id: str, dataset_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.one(
            "SELECT * FROM app_release_dataset_bindings WHERE release_id=? AND dataset_id=?",
            ((release_id or "").strip(), (dataset_id or "").strip()))
        if not row:
            return None
        out = dict(row)
        out["contract_bound"] = bool(row.get("contract_bound"))
        out["allowed_actions"] = tuple(
            a for a in str(row.get("allowed_actions") or "").split(",") if a)
        return out

    def allowed_actions(self, release_id: str, dataset_id: str) -> Optional[Tuple[str, ...]]:
        """이 릴리스에서 이 데이터셋에 허용된 행동.

        ★★★ 돌려주는 값이 셋이고 **셋 다 다른 뜻**이다:

            None   계약이 말한 적 없다(레거시 결속 또는 결속 없음) → 2차 판정 없음
            ()     계약이 «아무 행동도 허용하지 않는다» 고 말했다   → 전부 막힌다
            (…)    그 목록만 허용

        ⚠️ `None` 과 `()` 를 뭉개면 계약이 잠근 데이터셋이 열리거나, 레거시 앱이 통째로
          멈춘다. 둘 다 조용하다."""
        b = self.binding_for(release_id, dataset_id)
        if not b or not b["contract_bound"]:
            return None
        return b["allowed_actions"]

    def contract_coverage(self, release_id: str = "",
                          declared: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """계약이 **실제로 몇 개의 데이터셋을 잠그고 있는가.**

        ★★★ 분모는 **결속 행 수가 아니라 «선언»** 이다. 결속만 세면 계약이 열 개를
          선언했는데 하나만 물질화된 상태가 **「1/1 = 100%」** 로 보인다 — 가장 위험한
          거짓 초록이다. 그래서 분모를 `선언 → 물질화 → 결속` 셋으로 나눠 돌려준다.

        `declared` 는 계약이 선언한 데이터셋 이름들이다(계약 저장은 4단계이므로 지금은
        호출자가 넘긴다). 넘기지 않으면 `declared`·`missing` 은 `None` 이다 —
        ⚠️ 모르는 값을 0 으로 적지 않는다. 0 은 「선언이 없다」는 **사실**이고, 그것은
          「선언을 모른다」와 다르다."""
        rel = (release_id or "").strip()
        rows = self._store.query(
            "SELECT contract_bound AS b, runtime_name AS n FROM app_release_dataset_bindings"
            + (" WHERE release_id=?" if rel else ""), ((rel,) if rel else ()))
        bound = sum(1 for r in rows if int(r["b"] or 0))
        legacy = sum(1 for r in rows if not int(r["b"] or 0))
        out: Dict[str, Any] = {
            "materialized": bound + legacy,   # 결속된 데이터셋(= 실제로 존재하는 것)
            "bound": bound,                   # 그중 계약이 행동을 정한 것
            "legacy": legacy,                 # 계약 이전
            "total": bound + legacy,          # 하위호환 이름
            "declared": None, "missing": None, "undeclared": None,
        }
        if declared is not None:
            want = {str(d).strip() for d in declared if str(d).strip()}
            have = {str(r["n"] or "") for r in rows}
            out["declared"] = len(want)
            out["missing"] = sorted(want - have)      # 선언됐는데 물질화되지 않은 것
            out["undeclared"] = sorted(have - want)   # 계약에 없는데 결속돼 있는 것
        return out

    def legacy_identity_report(self) -> Dict[str, Any]:
        """★★★ **레거시 데이터셋의 앱 식별자를 어디까지 복원할 수 있는가.**

        마이그레이션은 `dataset_key=name` 만 채우고 `app_id` 는 **비워 둔다.** 그래서
        「앱을 개정해도 데이터가 유지된다」는 **신규 계약 데이터셋에만** 참이다. 기존 운영
        데이터는 아직 아니다 — 그 사실을 숫자로 드러내지 않으면 4단계에서 「다 됐다」고
        읽게 된다.

        ⚠️⚠️ **이름이 같다는 이유로 자동 연결하지 않는다.** 서로 다른 앱이 `orders` 라는
          이름을 쓰는 것은 흔한 일이고, 잘못 이으면 **남의 앱 레코드가 이 앱에 보인다.**
          그래서 이 함수는 **보고만 하고 아무것도 고치지 않는다.**

        돌려주는 다섯 갈래:

            recoverable   릴리스가 하나뿐이라 앱을 특정할 수 있다
            ambiguous     같은 이름이 여러 릴리스에 있어 후보가 여럿이다
            unbindable    결속이 없다(어느 릴리스도 가리키지 않는 고아)
            succeeded     이미 `app_id` 가 있다(계약 경로로 만들어진 것)
            quarantined   같은 (app_id, dataset_key) 가 둘 이상 — 승계 불가
        """
        rows = self._store.query(
            "SELECT d.dataset_id, d.name, d.app_id, d.dataset_key, "
            "       (SELECT COUNT(*) FROM app_release_dataset_bindings b "
            "          WHERE b.dataset_id = d.dataset_id) AS binds "
            "  FROM app_datasets d WHERE d.retired_at=''")
        by_key: Dict[Tuple[str, str], List[str]] = {}
        for r in rows:
            if str(r["app_id"] or ""):
                by_key.setdefault((str(r["app_id"]), str(r["dataset_key"] or "")), []).append(
                    str(r["dataset_id"]))
        dup = {k for k, v in by_key.items() if len(v) > 1}

        out: Dict[str, List[Dict[str, Any]]] = {
            "recoverable": [], "ambiguous": [], "unbindable": [],
            "succeeded": [], "quarantined": []}
        #: 같은 이름을 쓰는 데이터셋이 여럿이면 이름만으로는 앱을 특정할 수 없다.
        name_count: Dict[str, int] = {}
        for r in rows:
            if not str(r["app_id"] or ""):
                name_count[str(r["name"])] = name_count.get(str(r["name"]), 0) + 1

        for r in rows:
            item = {"dataset_id": str(r["dataset_id"]), "name": str(r["name"]),
                    "dataset_key": str(r["dataset_key"] or "")}
            app_id = str(r["app_id"] or "")
            if app_id:
                bucket = "quarantined" if (app_id, item["dataset_key"]) in dup else "succeeded"
            elif not int(r["binds"] or 0):
                bucket = "unbindable"
            elif name_count.get(item["name"], 0) > 1:
                bucket = "ambiguous"
            else:
                bucket = "recoverable"
            out[bucket].append(item)
        return {k: {"count": len(v), "items": v} for k, v in out.items()}

    def materialization_fingerprint(self, release_id: str) -> str:
        """★★★ **DB 결속 상태의 지문** — 계약 원문의 지문과 **다른 것**이다.

        계약서가 승인된 것과 DB 가 그대로 물질화된 것은 별개의 사실이다. 원문 지문만
        봉인하면 **「계약서는 승인됐지만 결속이 다른 상태」**를 잡을 수 없다 — 그때 앱은
        승인받은 계약과 다른 권한·다른 스키마로 돈다.

        들어가는 것: 각 결속의 `(런타임 이름, 데이터셋 키, 스키마 지문, 허용 행동)` 정렬본.
        ⚠️ 라벨·생성시각 같은 설명값은 넣지 않는다(§의미 지문과 같은 이유)."""
        rows = self._store.query(
            "SELECT b.runtime_name AS n, b.allowed_actions AS a, b.contract_bound AS c, "
            "       d.dataset_key AS k, COALESCE(v.schema_fingerprint,'') AS f "
            "  FROM app_release_dataset_bindings b "
            "  JOIN app_datasets d ON d.dataset_id = b.dataset_id "
            "  LEFT JOIN app_dataset_versions v ON v.version_id = b.version_id "
            " WHERE b.release_id=?", ((release_id or "").strip(),))
        material = sorted(
            [str(r["n"] or ""), str(r["k"] or ""), str(r["f"] or ""),
             str(r["a"] or ""), "1" if int(r["c"] or 0) else "0"] for r in rows)
        body = json.dumps(material, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    def adopt_dataset(self, app_id: str, dataset_key: str, release_id: str, *,
                      allowed_actions: Optional[Sequence[str]] = None,
                      schema: Any = None, contract_revision: int = 0
                      ) -> Optional[Dict[str, Any]]:
        """새 릴리스가 **같은 앱의 기존 데이터셋을 이어받는다.**

        ★★★ 이것이 「앱을 개정하면 현업 데이터가 안 보인다」를 고치는 지점이다.
          레코드는 `dataset_id` 에 매여 있고 그 id 는 릴리스를 넘어 그대로다.

        ⚠️ `app_id` 나 `dataset_key` 가 비면 **아무것도 이어받지 않는다** — 빈 값으로
          맞추면 서로 다른 앱의 데이터셋이 하나로 묶인다."""
        app_id = (app_id or "").strip()
        dataset_key = (dataset_key or "").strip()
        if not app_id or not dataset_key:
            return None
        with self._store.transaction() as conn:
            rows = self._store.rows(
                conn, "SELECT dataset_id, name FROM app_datasets "
                      " WHERE app_id=? AND dataset_key=? AND retired_at=''",
                (app_id, dataset_key))
            if not rows:
                return None
            if len(rows) > 1:
                #: ★★★ **첫 행을 고르지 않는다.** 그 선택은 임의이고 조용하며, 고른 쪽이
                #:   틀렸다면 현업 레코드가 통째로 다른 데이터셋에 붙는다.
                #:   유일성 인덱스가 있으면 여기 오지 않는다 — 오면 그 인덱스가 걸리지
                #:   못한 상태라는 뜻이고, 그 사실이 드러나야 한다.
                raise AppDataError(
                    f"앱 {app_id} 에 «{dataset_key}» 가 {len(rows)}개 있습니다 "
                    f"({[r['dataset_id'] for r in rows]}) — 어느 것을 이어받을지 "
                    f"고를 수 없습니다. 중복을 먼저 정리해야 합니다.")
            did = str(rows[0]["dataset_id"])
            self._bind_in_tx(conn, (release_id or "").strip(), did,
                             runtime_name=str(rows[0]["name"]),
                             allowed_actions=allowed_actions, schema=schema,
                             contract_revision=contract_revision)
        return self.get_dataset(did)

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.one("SELECT * FROM app_datasets WHERE dataset_id=?", (dataset_id,))
        return self._dataset_view(row) if row else None

    def find_dataset(self, release_id: str, name: str) -> Optional[Dict[str, Any]]:
        """★ 앱은 **이름으로만** 데이터셋을 부른다(설계 §7 규칙 4).

        `release_id` 는 호스트가 붙인다 — 앱이 자기 릴리스를 말하게 하면 남의 앱 데이터를
        요청할 수 있다.

        ★★★ [I-4 2단계] **결속(binding)을 지나** 찾는다. 종전처럼
        `app_datasets.release_id` 를 직접 보면 앱을 개정한 순간 같은 이름의 데이터셋을
        못 찾고 새로 만들어, **현업이 쌓은 레코드가 승계되지 않는다.**

        ★★★ [2.1 보정] 돌려주는 `schema` 는 **이 릴리스가 결속한 판**이다.
        ⚠️ 데이터셋 마스터의 `schema_json` 을 그대로 주면, 릴리스 v1·v2 가 서로 다른 판을
          가리켜도 **둘 다 마지막에 저장된 스키마 하나**로 검증된다. 즉 판을 기록만 하고
          쓰지 않는 상태였고, 그것은 판이 없는 것과 같다."""
        row = self._store.one(
            "SELECT d.*, b.version_id AS _bound_version_id, b.runtime_name AS _runtime_name "
            "  FROM app_datasets d "
            "  JOIN app_release_dataset_bindings b ON b.dataset_id = d.dataset_id "
            " WHERE b.release_id=? AND b.runtime_name=?",
            ((release_id or "").strip(), (name or "").strip()))
        if not row:
            return None
        vid = str(row.pop("_bound_version_id", "") or "")
        row.pop("_runtime_name", None)
        out = self._dataset_view(row)
        out["bound_version_id"] = vid
        if vid:
            ver = self._store.one(
                "SELECT schema_json, contract_revision, schema_fingerprint "
                "  FROM app_dataset_versions WHERE version_id=?", (vid,))
            if ver:
                out["schema"] = _load_schema(ver["schema_json"])
                out["contract_revision"] = int(ver["contract_revision"] or 0)
                out["schema_fingerprint"] = str(ver["schema_fingerprint"] or "")
        return out

    def list_datasets(self, release_id: str = "", include_retired: bool = False
                      ) -> List[Dict[str, Any]]:
        params: List[Any] = []
        if release_id:
            sql = ("SELECT d.* FROM app_datasets d "
                   "  JOIN app_release_dataset_bindings b ON b.dataset_id = d.dataset_id "
                   " WHERE b.release_id=?")
            params.append(release_id.strip())
        else:
            sql = "SELECT d.* FROM app_datasets d WHERE 1=1"
        if not include_retired:
            sql += " AND d.retired_at=''"
        sql += " ORDER BY d.created_at DESC"
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
        #: ★★★ [2.1 보정] **계약이 정한 데이터셋은 여기서 바꾸지 않는다.**
        #:
        #: ⚠️ 관리 API 의 전역 스키마 변경과 릴리스별 계약 판은 **다른 경로**다. 둘을
        #:   섞으면 「승인된 계약 revision 의 내용이 콘솔에서 바뀌는」 상태가 되고,
        #:   승인 원장은 그 변경을 모른다. 계약을 고치려면 계약을 개정해야 한다.
        bound = self._store.scalar(
            "SELECT COUNT(*) FROM app_release_dataset_bindings "
            " WHERE dataset_id=? AND contract_bound=1", (dataset_id,)) or 0
        if bound:
            raise AppDataError(
                f"이 데이터셋은 계약이 정합니다(결속 {bound}건) — 콘솔에서 스키마를 바꿀 수 "
                f"없습니다. 계약을 개정하고 새 revision 으로 결속하십시오.")
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
    def create_record(self, dataset_id: str, payload: Any, *, actor_id: str,
                      release_id: str = "") -> Dict[str, Any]:
        """★★★ [2.1 보정] `release_id` 를 주면 **그 릴리스가 결속한 판**으로 검증한다.

        ⚠️ 주지 않으면 데이터셋 마스터 스키마를 쓴다(콘솔·관리 경로). 런타임은 **반드시**
          넘긴다 — 넘기지 않으면 v1 과 v2 가 서로 다른 판을 가리켜도 둘 다 마지막에
          저장된 스키마 하나로 검증되고, 판을 기록만 하고 쓰지 않는 상태가 된다."""
        ds = self._require_active(dataset_id, release_id=release_id)
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

    def update_record(self, record_id: str, payload: Any, *, actor_id: str,
                      release_id: str = "") -> Dict[str, Any]:
        """`release_id` 의 뜻은 `create_record` 와 같다 — 결속된 판으로 검증한다."""
        row = self._store.one("SELECT * FROM app_records WHERE record_id=?", (record_id,))
        if not row:
            raise AppDataError("레코드를 찾을 수 없습니다.")
        if row["deleted_at"]:
            raise AppDataError("삭제된 레코드는 수정할 수 없습니다.")
        if not (actor_id or "").strip():
            raise AppDataError("레코드 수정에는 주체(actor_id)가 필요합니다.")
        ds = self._require_active(row["dataset_id"], release_id=release_id)
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
    def _require_active(self, dataset_id: str, *, release_id: str = "") -> Dict[str, Any]:
        """살아 있는 데이터셋 + **이 릴리스가 쓰는 스키마 판**.

        ★ 판 해석을 여기 한 곳에 둔다. 호출부가 스키마를 골라 넘기게 하면 언젠가 한
          호출부가 «마스터» 를 넘기고, 그 경로만 계약 밖 필드를 받게 된다."""
        ds = self.get_dataset(dataset_id)
        if not ds:
            raise AppDataError("데이터셋을 찾을 수 없습니다.")
        if ds["retired_at"]:
            raise AppDataError("폐지된 데이터셋에는 쓸 수 없습니다.")
        rel = (release_id or "").strip()
        if rel:
            b = self.binding_for(rel, dataset_id)
            vid = str((b or {}).get("version_id") or "")
            if vid:
                ver = self._store.one(
                    "SELECT schema_json, contract_revision, schema_fingerprint "
                    "  FROM app_dataset_versions WHERE version_id=?", (vid,))
                if ver:
                    ds["schema"] = _load_schema(ver["schema_json"])
                    ds["contract_revision"] = int(ver["contract_revision"] or 0)
                    ds["schema_fingerprint"] = str(ver["schema_fingerprint"] or "")
        return ds

    @staticmethod
    def _dataset_view(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["schema"] = _load_schema(out.pop("schema_json", ""))
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
