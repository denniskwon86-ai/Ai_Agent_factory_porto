# -*- coding: utf-8 -*-
"""[P2 · DEP-06/05] **서빙 준비도** — 이 노드에 트래픽을 넘겨도 되는가.

## 이름부터 — `release_readiness` 와 **다른 것**이다

`core/release_readiness.py` 는 「이 **릴리스**를 운영에 둬도 되는가」(§8.2 업무 체크리스트)다.
이 모듈은 「이 **노드**가 지금 트래픽을 받아도 되는가」다. 둘을 한 낱말로 부르면 승격 판정이
반드시 어긋난다 — 업무 체크리스트가 통과했다고 프로세스가 준비된 것이 아니고, 그 반대도 같다.

## 생존 · 준비 · 업무 수용은 **별개**다

    생존   프로세스가 응답한다                      → 기존 `/api/v1/health` 가 한다
    준비   이 노드가 «올바른 것» 을 들고 서 있다     → 여기
    업무   실제 업무가 통과한다                      → 별도 probe

⚠️ **200 만으로 트래픽을 넘기지 않는다**(DEP-06). health 는 DB 도 인증도 보지 않는다 —
  그것은 일부러 그런 것이고, 그래서 승격 판정의 근거가 될 수 없다.

## 세 값뿐이다 — `READY` · `FAIL` · `UNKNOWN`

★★ **`UNKNOWN` 은 「모른다」이지 「안 됐다」가 아니다.** 그리고 **둘 다 승격시키지 않는다.**
  확인하지 못한 것을 통과로 두지 않는 것이 이 저장소의 관통 원칙이고, 반대로 「모른다」를
  「실패」로 접으면 원인을 못 찾는다.

## 이 판정이 **하지 않는** 것

    · 외부 LLM 호출 0
    · 자료 seed 0 · DDL 0 · 마이그레이션 0
    · **없는 DB 파일을 만들지 않는다** — `mode=ro` 로만 연다(sqlite3 기본 연결은 파일을
      «만든다». 준비도 점검이 저장소를 만들어 버리면 그 점검이 곧 사고다)
    · 설치 «적용» 을 하지 않는다 — 읽기 검증만(DEP-05: 읽기 검증 / 승인된 초기 설치 분리)

## 응답에 무엇을 싣지 않는가

경로·SQL·접속 정보·tenant 원문을 **싣지 않는다.** 사유는 **닫힌 코드 목록**으로만 말한다 —
준비도 응답은 승격 자동화가 읽는 곳이고, 거기에 내부 구조를 실으면 그게 정찰 창구가 된다.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

READY = "READY"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
VERDICTS = (READY, FAIL, UNKNOWN)

#: 사유는 **닫힌 목록**이다. 자유 문장을 쓰면 거기에 경로가 새어 나간다.
REASON_OK = "ok"
REASON_IDENTITY_ABSENT = "release_identity_absent"
REASON_IDENTITY_MISMATCH = "release_identity_mismatch"
REASON_SCHEMA_STORE_ABSENT = "schema_store_absent"
REASON_SCHEMA_OBJECTS_MISSING = "schema_objects_missing"
REASON_SCHEMA_UNREADABLE = "schema_unreadable"
REASON_STORE_QUERY_FAILED = "store_query_failed"
REASON_SHARED_STORAGE_ABSENT = "shared_storage_absent"
REASON_SHARED_STORAGE_UNVERIFIED = "shared_storage_unverified"
REASON_INSTALL_CONTEXT_ABSENT = "install_context_absent"
REASON_INSTALL_CONTEXT_MISMATCH = "install_context_mismatch"
REASON_INSTALL_CONTEXT_UNREADABLE = "install_context_unreadable"
REASON_ROLE_NOT_STARTED = "role_not_started"

#: 공유 저장소가 «정말 공유» 인지는 설치가 놓는 표식으로만 말한다(§check_shared_storage).
SHARED_MARKER = ".afs-shared"


@dataclass(frozen=True)
class Check:
    """검사 하나. **사유는 코드**이고 세부는 담지 않는다."""
    name: str
    verdict: str
    reason: str = REASON_OK

    def as_dict(self) -> Dict[str, str]:
        return {"name": self.name, "verdict": self.verdict, "reason": self.reason}


@dataclass
class Report:
    checks: List[Check] = field(default_factory=list)
    artifact_digest: str = ""
    config_fingerprint: str = ""

    @property
    def verdict(self) -> str:
        """★ 하나라도 FAIL 이면 FAIL. FAIL 이 없고 UNKNOWN 이 있으면 UNKNOWN.

        ⚠️ UNKNOWN 을 READY 쪽으로도 FAIL 쪽으로도 **접지 않는다.**"""
        kinds = {c.verdict for c in self.checks}
        if not self.checks:
            #: 아무것도 보지 않고 「준비됨」이라고 말하지 않는다.
            return UNKNOWN
        if FAIL in kinds:
            return FAIL
        if UNKNOWN in kinds:
            return UNKNOWN
        return READY

    def as_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict,
                "artifact_digest": self.artifact_digest,
                "config_fingerprint": self.config_fingerprint,
                "checks": [c.as_dict() for c in self.checks]}


def may_promote(report: "Report") -> bool:
    """★★ **`READY` 하나만 참이다.** `UNKNOWN` 은 승격 사유가 되지 못한다."""
    return report.verdict == READY


# ── ① 릴리스·설정 식별 ───────────────────────────────────────────────────
def check_release_identity(running_digest: str, running_config: str,
                           expected_digest: str = "",
                           expected_config: str = "") -> Check:
    """이 프로세스가 **무엇을 들고** 서 있는지 말할 수 있는가.

    ⚠️ 말하지 못하면 `UNKNOWN` 이다 — 「아마 맞겠지」로 승격하면, 나중에 무엇이 돌았는지
      아무도 답하지 못한다. 요구값이 주어졌는데 다르면 그건 `FAIL` 이다."""
    if not (running_digest or "").strip() or not (running_config or "").strip():
        return Check("release_identity", UNKNOWN, REASON_IDENTITY_ABSENT)
    if expected_digest and expected_digest != running_digest:
        return Check("release_identity", FAIL, REASON_IDENTITY_MISMATCH)
    if expected_config and expected_config != running_config:
        return Check("release_identity", FAIL, REASON_IDENTITY_MISMATCH)
    return Check("release_identity", READY)


# ── ② 스키마 지원 범위 ───────────────────────────────────────────────────
def _open_readonly(path: str) -> sqlite3.Connection:
    """⚠️⚠️ **없는 파일을 만들지 않는다.** `sqlite3.connect(path)` 는 파일을 «만든다» —

    준비도 점검이 저장소를 만들어 놓으면 그 점검 자체가 사고다.

    ⚠️ URI 를 **문자열로 이어 붙이지 않는다.** `f"file:{path}?mode=ro"` 는 Windows
      역슬래시 경로에서 URI 가 아니고, 경로에 `?`·`#` 가 있으면 질의부터 잘려 나간다.
      `as_uri()` 가 escape 까지 해 준다."""
    uri = Path(os.path.abspath(path)).as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=3)


def check_schema(required: Mapping[str, Mapping[str, Sequence[str]]],
                 resolve: Callable[[str], str]) -> Check:
    """코드가 **필요로 하는** 표·열이 실제 저장소에 있는가. 읽기 전용.

    `required` = {저장소키: {표이름: (열, …)}}. 열 목록이 비면 표 존재만 본다.
    ★ [Z05] 「Green 준비 실패·DB schema 불일치」의 판정 지점이 여기다."""
    for store_key, tables in required.items():
        path = resolve(store_key)
        if not path or not os.path.isfile(path):
            #: 파일이 없다 — **연결하지 않는다**(연결하면 만들어진다).
            return Check("schema", FAIL, REASON_SCHEMA_STORE_ABSENT)
        try:
            conn = _open_readonly(path)
        except (sqlite3.Error, OSError):
            #: ⚠️ `OSError` 도 잡는다 — 배포 뒤 **파일 소유권이 틀리면** 권한 오류가 난다.
            #:   준비도 점검이 거기서 죽으면 승격 판정 자체를 못 얻는다. 「모른다」로 답한다.
            return Check("schema", UNKNOWN, REASON_SCHEMA_UNREADABLE)
        try:
            for table, columns in tables.items():
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)).fetchone()
                if row is None:
                    return Check("schema", FAIL, REASON_SCHEMA_OBJECTS_MISSING)
                if columns:
                    have = {r[1] for r in conn.execute(
                        f"PRAGMA table_info({table})").fetchall()}
                    if not set(columns) <= have:
                        return Check("schema", FAIL, REASON_SCHEMA_OBJECTS_MISSING)
        except sqlite3.Error:
            return Check("schema", UNKNOWN, REASON_SCHEMA_UNREADABLE)
        finally:
            conn.close()
    return Check("schema", READY)


# ── ③ 저장소 제한 조회 ───────────────────────────────────────────────────
def check_bounded_query(probes: Iterable[Tuple[str, str]],
                        resolve: Callable[[str], str]) -> Check:
    """**값이 아니라 도달** 을 본다 — `LIMIT 1` 짜리 읽기 하나.

    ⚠️ 쓰기 탐침을 하지 않는다. 준비도 확인이 자료를 남기면 그건 더 이상 확인이 아니다."""
    for store_key, table in probes:
        path = resolve(store_key)
        if not path or not os.path.isfile(path):
            return Check("bounded_query", FAIL, REASON_SCHEMA_STORE_ABSENT)
        try:
            conn = _open_readonly(path)
        except (sqlite3.Error, OSError):
            #: 열지 못한 것은 «틀렸다» 가 아니라 «모른다» 다.
            return Check("bounded_query", UNKNOWN, REASON_SCHEMA_UNREADABLE)
        try:
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
        except sqlite3.Error:
            #: 열렸는데 질의가 안 된다 — 그건 확인된 실패다.
            return Check("bounded_query", FAIL, REASON_STORE_QUERY_FAILED)
        finally:
            conn.close()
    return Check("bounded_query", READY)


# ── ④ 공유 저장소 ────────────────────────────────────────────────────────
def check_shared_storage(directories: Iterable[str]) -> Check:
    """여러 노드가 **같은 것을 보고 있는가.**

    ⚠️ 쓸 수 있는지는 **쓰기로 확인하지 않는다.** 대신 설치가 놓는 표식(`.afs-shared`)을
      본다. 표식이 없으면 `UNKNOWN` 이다 — 「아마 공유겠지」로 승격하면 전환 뒤에
      한쪽 노드만 파일을 못 보는 사고가 조용히 생긴다."""
    verdict = READY
    for folder in directories:
        if not folder or not os.path.isdir(folder):
            return Check("shared_storage", FAIL, REASON_SHARED_STORAGE_ABSENT)
        if not os.path.exists(os.path.join(folder, SHARED_MARKER)):
            verdict = UNKNOWN
    return Check("shared_storage", verdict,
                 REASON_OK if verdict == READY else REASON_SHARED_STORAGE_UNVERIFIED)


# ── ⑤ 설치 문맥 — **읽기 검증만** (DEP-05) ───────────────────────────────
def check_install_context(settings_path: str,
                          load_settings: Callable[[str], Mapping[str, Any]],
                          observed_tenant: Optional[str]) -> Check:
    """선언한 tenant 와 저장소가 보는 tenant 가 같은가.

    ⚠️⚠️ **적용하지 않는다.** `apply_settings` 는 `organization_nodes` 를 다시 쓴다 —
      준비도 점검이 그것을 부르면 점검이 조직을 바꾼다. 여기서는 읽기만 한다."""
    try:
        settings = load_settings(settings_path) or {}
    except Exception:  # noqa: BLE001 — 읽기 실패는 «모른다»지 «틀렸다»가 아니다.
        return Check("install_context", UNKNOWN, REASON_INSTALL_CONTEXT_UNREADABLE)
    declared = str(settings.get("tenant_id", "") or "").strip()
    if not declared:
        return Check("install_context", FAIL, REASON_INSTALL_CONTEXT_ABSENT)
    if not (observed_tenant or "").strip():
        return Check("install_context", UNKNOWN, REASON_INSTALL_CONTEXT_UNREADABLE)
    if declared != observed_tenant:
        return Check("install_context", FAIL, REASON_INSTALL_CONTEXT_MISMATCH)
    return Check("install_context", READY)


# ── ⑥ 역할 기동 ─────────────────────────────────────────────────────────
def check_roles(declared: Iterable[str], started: Iterable[str]) -> Check:
    """이 노드가 맡기로 한 역할이 **실제로 떠 있는가.**

    ⚠️ 선언이 «비어 있으면» READY 가 아니라 `UNKNOWN` 이다. 아무 역할도 적지 않은 노드는
      「할 일이 없어서 준비된」 것이 아니라 **무엇을 해야 하는지 모르는** 것이다.
      빈 집합끼리 비교하면 공짜 초록이 나온다 — 그 공짜가 관문을 무력화한다."""
    declared_set, started_set = set(declared), set(started)
    if not declared_set:
        return Check("roles", UNKNOWN, REASON_ROLE_NOT_STARTED)
    missing = declared_set - started_set
    return Check("roles", FAIL if missing else READY,
                 REASON_ROLE_NOT_STARTED if missing else REASON_OK)


# ── 실제 저장소에 배선 ──────────────────────────────────────────────────
#: ⚠️ 여기 적는 열 이름은 **정본 DDL 에서 확인한 것**이다. 내 기억으로 적으면 건강한
#:   시스템에 «거짓 경보» 를 울리고, 그 경보는 곧 무시된다 — 그러면 관문이 없는 것과 같다.
REQUIRED_SCHEMA: Dict[str, Dict[str, Sequence[str]]] = {
    "auth": {
        "auth_credential": ("user_id", "salt", "hash"),
        "auth_session": (),
        #: 1회 소비 계약이 걸린 열들 — 이관 대사 1순위이기도 하다.
        "auth_sse_ticket": ("token_hash", "consumed_at", "audience", "expires_at"),
    },
    "enterprise_context": {
        "tenants": (),
        "organization_nodes": ("node_id", "entity_id", "tenant_id"),
    },
}

#: 도달만 본다 — 값이 아니라 «읽을 수 있는가».
BOUNDED_PROBES = (("auth", "auth_credential"), ("enterprise_context", "tenants"))


def default_store_paths() -> Dict[str, str]:
    from core.paths import data_path
    return {"auth": data_path("auth.db"),
            "enterprise_context": data_path("enterprise_context.db")}


def observed_tenant_of(ecm_db_path: str, legal_node_id: str) -> str:
    """법인 홈 노드가 **실제로 어느 tenant 에 묶여 있는지.** 읽기 전용.

    ★ [DEP-05] 설치 설정은 tenant 를 말하는데 노드가 옛 tenant 에 묶여 있으면,
      인증 세션과 ECM 이 서로 다른 회사를 말한다 — 화면은 멀쩡해 보이고 권한만 갈린다."""
    if not legal_node_id or not os.path.isfile(ecm_db_path):
        return ""
    try:
        conn = _open_readonly(ecm_db_path)
    except (sqlite3.Error, OSError):
        return ""
    try:
        row = conn.execute("SELECT tenant_id FROM organization_nodes WHERE node_id=?",
                           (legal_node_id,)).fetchone()
        return str(row[0]) if row else ""
    except sqlite3.Error:
        return ""
    finally:
        conn.close()


def collect(*, settings_path: str, shared_dirs: Iterable[str],
            declared_roles: Iterable[str], started_roles: Iterable[str],
            running_digest: str = "", running_config: str = "",
            expected_digest: str = "", expected_config: str = "",
            stores: Optional[Mapping[str, str]] = None,
            load_settings: Optional[Callable[[str], Mapping[str, Any]]] = None) -> Report:
    """여섯 검사를 실제 저장소·설정 위에서 돌린다. **읽기만 한다.**"""
    paths = dict(stores or default_store_paths())
    if load_settings is None:
        from core.installation_context import load_settings as _load
        load_settings = _load

    try:
        settings = load_settings(settings_path) or {}
    except Exception:  # noqa: BLE001
        settings = {}
    legal_node_id = str((settings.get("organization") or {}).get("legal_node_id", "")
                        or "").strip()
    observed = observed_tenant_of(paths.get("enterprise_context", ""), legal_node_id)

    return build_report([
        check_release_identity(running_digest, running_config,
                               expected_digest, expected_config),
        check_schema(REQUIRED_SCHEMA, lambda key: paths.get(key, "")),
        check_bounded_query(BOUNDED_PROBES, lambda key: paths.get(key, "")),
        check_shared_storage(shared_dirs),
        check_install_context(settings_path, load_settings, observed),
        check_roles(declared_roles, started_roles),
    ], artifact_digest=running_digest, config_fingerprint=running_config)


def build_report(checks: Iterable[Check], *, artifact_digest: str = "",
                 config_fingerprint: str = "") -> Report:
    return Report(list(checks), artifact_digest, config_fingerprint)
