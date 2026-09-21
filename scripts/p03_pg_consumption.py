# -*- coding: utf-8 -*-
"""[P03.2 / P03.3] **실제 PostgreSQL 에서** 제품 경로를 소비한다.

    설치(installer 역할) ──▶ 로그인 · 세션 · 문맥 · 거절 ──▶ 티켓 단일/동시 소비
                                                        ──▶ 프로세스 재시작 · 대사

## 이 파일이 지키는 것

★ **제품 함수를 부른다.** `AuthStore` · `EcmRepository` 의 실제 메서드다. 이 파일이
  SQL 을 다시 쓰면 제품이 아닌 것을 재게 된다.
★ 연결은 `core.db.postgres_factory()` — **방언을 스스로 말하고** 행 형식(dict)을 고정한다.
  환경변수로 방언을 추측하지 않는다.
★ **동시 소비는 연결을 스레드마다 새로 연다.** 하나를 공유하면 드라이버가 직렬화해
  「정확히 하나」가 DB 덕분인지 연결 덕분인지 구분할 수 없다.
★ **재시작은 «프로세스» 를 새로 띄워 확인한다.** `phase2` 를 따로 실행한다 — 같은
  프로세스에서 연결만 다시 여는 것은 재시작 증거가 아니다.

## 경계

⚠️ 접속 정보는 launcher 가 자식 환경에만 넣는다. 이 파일은 DSN 을 **읽지도 찍지도** 않는다.
⚠️ 운영 `data/` 를 열지 않는다. 파일 경로가 필요한 자리에는 임시 경로만 준다
  (관리 모드 + 주입 연결이라 실제로는 파일을 쓰지 않는다).
⚠️ 합성 계정·합성 조직만 쓴다(`.invalid` / `_pg`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: ⚠️ 관리 모드는 **생성자 인자로만** 켠다(`managed=True`). 예전에 여기서 전역
#:   환경변수를 세웠는데, 그러면 **이 모듈을 import 하는 것만으로** 남의 시험까지
#:   관리 모드가 되어 22건이 깨졌다. 같은 사고를 두 번 내지 않는다.

from core.auth import DEFAULT_PASSWORD  # noqa: E402
from core.db import postgres_factory  # noqa: E402
from core.db.managed_schema import ddl_statements  # noqa: E402

USER = "pg-probe@example.invalid"
PASSWORD = "synthetic-pg-001"
TENANT = "t_pg"
ENTITY = "e_pg"
ROOT_NODE = "n_pg_root"
CHILD_NODE = "n_pg_child"


class RecordingFactory:
    """실행된 SQL 을 세는 껍데기. **방언 선언을 그대로 물려준다.**

    ⚠️ `.backend` 를 잃으면 store 가 방언을 모르게 되고, 그러면 환경변수 추측으로
      되돌아간다. 껍데기가 계약을 깎아먹지 않도록 그대로 넘긴다."""

    def __init__(self, inner, log: List[str]):
        self._inner = inner
        self.backend = inner.backend
        self.describe = inner.describe
        self._log = log

    def __call__(self):
        return _RecordingConnection(self._inner(), self._log)


class _RecordingConnection:
    def __init__(self, raw, log: List[str]):
        self._raw = raw
        self._log = log

    def execute(self, sql, *args, **kwargs):
        self._log.append(sql)
        return self._raw.execute(sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        self._log.append(sql)
        return self._raw.executemany(sql, *args, **kwargs)

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *exc):
        return self._raw.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._raw, name)


def _stores(log: Optional[List[str]] = None):
    """제품 store 를 **실제 PG 연결**로 세운다."""
    from core.auth import AuthStore
    from core.enterprise_context.repository import EcmRepository

    factory = postgres_factory()
    if log is not None:
        factory = RecordingFactory(factory, log)
    #: ⚠️ 관리 모드 + 주입 연결이라 이 경로로 파일을 열지 않는다. 그래도 운영 `data/` 를
    #:   가리키지 않도록 임시 경로를 준다.
    scratch = tempfile.gettempdir()
    auth = AuthStore(db_path=os.path.join(scratch, "unused-auth.db"),
                     connect=factory, managed=True)
    ecm = EcmRepository(db_path=os.path.join(scratch, "unused-ecm.db"),
                        connect=factory, managed=True)
    return auth, ecm, factory


def identity() -> Dict[str, str]:
    """이 연결이 «무엇에» 붙었는지. 증거에 남긴다(비밀은 없다).

    ★ `managed_schema` 의 PG 가지도 **여기서 같이 불러 본다.** 그 가지들은 「한 번도
      실행되지 않았다」고 주석에 적혀 있었다 — 그 문장을 지우려면 돌았다는 증거가
      있어야지, 돌았을 «것 같다» 로 지우면 안 된다."""
    from core.db.managed_schema import (STORE_AUTH, backend_of, missing_objects_on,
                                        target_identity)
    factory = postgres_factory()
    conn = factory()
    try:
        row = conn.execute("SELECT current_database() AS db, current_schema() AS schema, "
                           "current_user AS who").fetchone()
        out = {k: str(row[k]) for k in ("db", "schema", "who")}
        out["backend_of"] = backend_of(conn, factory)
        out["target_identity"] = target_identity(conn, out["backend_of"])
        out["missing_objects_auth"] = str(
            missing_objects_on(conn, STORE_AUTH, backend=out["backend_of"]))
        return out
    finally:
        conn.close()


def seed_context(ecm) -> Dict[str, Any]:
    """조직을 세운다 — **제품의 쓰기 API 로만** 한다.

    ★★ 처음에는 여기서 손으로 INSERT 를 썼다. 그러면 읽기만 제품 경로이고 쓰기는
      내가 지어낸 SQL 이라, **제품의 UPSERT 가 PG 에서 도는지** 하나도 증명되지 않는다.
      제품은 `ON CONFLICT(node_id, code)` · `ON CONFLICT(from_node_id, to_node_id,
      relation_type, effective_from)` 같은 **복합 충돌 대상**을 쓰는데, 설치 스키마에
      대응 제약이 없으면 바로 그 자리에서 깨진다. 그 자리를 실제로 두드린다.

    ⚠️ 두 번 돌려도 같아야 한다 — UPSERT 이므로 되풀이가 곧 두 번째 확인이다."""
    from core.enterprise_context.models import (STATUS_ACTIVE, REL_OPERATING_PARENT,
                                                EnterpriseEntity, OrganizationEdge,
                                                OrganizationNode)
    ecm.upsert_tenant(TENANT, "합성PG테넌트")
    ecm.upsert_entity(EnterpriseEntity(entity_id=ENTITY, tenant_id=TENANT,
                                       entity_type="legal_entity", entity_mode="REAL",
                                       name_ko="합성PG법인", status=STATUS_ACTIVE))
    for node, name, code in ((ROOT_NODE, "합성PG본부", "PGROOT"),
                             (CHILD_NODE, "합성PG팀", "PGCHILD")):
        ecm.upsert_node(OrganizationNode(node_id=node, entity_id=ENTITY, tenant_id=TENANT,
                                         node_type="business_division", code=code,
                                         name_ko=name, status=STATUS_ACTIVE))
    ecm.add_edge(OrganizationEdge(edge_id="edge_pg_1", tenant_id=TENANT,
                                  from_node_id=ROOT_NODE, to_node_id=CHILD_NODE,
                                  relation_type=REL_OPERATING_PARENT,
                                  status=STATUS_ACTIVE))
    approved = ecm.approve_entity(ENTITY, "pg-probe@example.invalid")

    #: ★★ 별칭 이력은 코드가 **바뀔 때** 옛 코드를 남긴다 — 처음 붙일 때는 안 남는다.
    #:   그래서 여기서 한 번 바꿔야 `ON CONFLICT(node_id, code)` 를 실제로 친다. 안 치면
    #:   「복합 충돌 대상이 PG 에서 성립하는가」가 통째로 미검증으로 남는다.
    #:   ⚠️ 되풀이 실행에서도 매번 «바뀌도록» 두 번 돌린다. 두 번째 실행에서는 별칭 행이
    #:     이미 있으므로 `DO UPDATE` 쪽 가지까지 지난다.
    current = ecm.get_node(ROOT_NODE)
    for code in ("PGROOT", "PGROOT2"):
        if (current.code or "") != code:
            current = ecm.upsert_node(
                OrganizationNode(**{**current.model_dump(), "code": code}))

    aliases = ecm.code_aliases_of(ROOT_NODE)
    return {
        "upsert_is_idempotent": ecm.get_node(ROOT_NODE).name_ko == "합성PG본부",
        "edge_children": ecm.children(ROOT_NODE, REL_OPERATING_PARENT),
        "edge_parents": ecm.parents(CHILD_NODE, REL_OPERATING_PARENT),
        "alias_history_after_code_change": [a["code"] for a in aliases],
        "alias_lookup_finds_old_code": [
            n.node_id for n in ecm.find_nodes_by_code_alias("PGROOT")],
        "find_by_current_code": getattr(ecm.find_node_by_code("PGROOT2", tenant_id=TENANT),
                                        "node_id", None),
        "entity_approved_status": getattr(approved, "status", None),
    }


def probe_profile_path(ecm) -> Dict[str, Any]:
    """★★ 첫 경로 **밖의** 표를 제품이 건드리면 어떻게 되는가.

    저장소는 `enterprise_profiles` · `enterprise_process_heads` 도 쓰는데, 이 둘은
    설치 스키마에도 `REQUIRED` 에도 없다. 즉 관리 모드 확인은 「설치됨」이라고 말하고
    제품 호출은 깨진다. **주장하지 말고 눌러 본다** — 소스를 읽어 낸 판단은 증거가 아니다."""
    out: Dict[str, Any] = {}
    try:
        out["list_profiles"] = f"{len(ecm.list_profiles())}건"
    except Exception as exc:  # noqa: BLE001 — 무엇으로 깨지는지가 바로 결과다
        out["list_profiles"] = type(exc).__name__
    try:
        ecm.assert_legacy_process_reader(ROOT_NODE)
        out["assert_legacy_process_reader"] = "통과"
    except Exception as exc:  # noqa: BLE001
        out["assert_legacy_process_reader"] = type(exc).__name__
    return out


def runtime_ddl_is_refused_by_the_database() -> Dict[str, Any]:
    """★★ 「runtime DDL 0」을 **DB 가 강제하는지** 본다.

    지금까지는 내가 SQL 을 세어 보인 것뿐이었다. 권한이 분리되면 **DB 가 거절하는 것**을
    증거로 쓸 수 있다 — 응용이 실수로 시도해도 못 들어간다."""
    outcome: Dict[str, Any] = {}
    for label, sql in (("CREATE TABLE", "CREATE TABLE probe_should_fail(a text)"),
                       ("CREATE TEMP TABLE", "CREATE TEMP TABLE probe_tmp(a text)"),
                       ("ALTER TABLE", "ALTER TABLE tenants ADD COLUMN probe text")):
        conn = postgres_factory()()
        try:
            conn.execute(sql)
            conn.commit()
            outcome[label] = "통과해 버림(계약 위반)"
        except Exception as exc:  # noqa: BLE001 — 거절이 기대값이다
            outcome[label] = type(exc).__name__
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            conn.close()
    return outcome


# ── 1단계: 로그인 · 문맥 · 티켓 ─────────────────────────────────────────
def phase_login_and_tickets() -> Dict[str, Any]:
    log: List[str] = []
    auth, ecm, _ = _stores(log)
    result: Dict[str, Any] = {"identity": identity()}

    #: ⚠️ 행이 «없을 때» 제품은 초기 공통 비밀번호와 대조한다. 그래서 「저장한 해시로
    #:   맞췄다」를 주장하려면 **행의 유무**를 함께 적어야 한다. 실행을 되풀이하면 앞
    #:   실행이 남긴 행 때문에 앞뒤가 달라지는데, 그것을 기본값 동작으로 읽으면 틀린다.
    row_existed = not auth.uses_default_password(USER)
    auth.set_password(USER, PASSWORD)
    result["password"] = {
        "credential_row_existed_before_this_run": row_existed,
        #: 한 번도 저장한 적 없는 사용자만이 기본 비밀번호 경로를 탄다 — 실행 순서와
        #: 무관한 불변식이라 되풀이해도 같은 값이다.
        "never_set_user_falls_back_to_default": auth.verify(
            "never-set@example.invalid", DEFAULT_PASSWORD),
        "never_set_user_rejects_other": auth.verify(
            "never-set@example.invalid", PASSWORD),
        "correct": auth.verify(USER, PASSWORD),
        "wrong": auth.verify(USER, "틀린값"),
        #: 한글 비밀번호가 500 이 아니라 False 로 떨어지는지 — PG 에서도 같은지 본다.
        "korean_wrong_is_false_not_crash": auth.verify(USER, "틀린비밀번호"),
        "unknown_user_not_our_password": auth.verify("nobody@example.invalid", PASSWORD),
    }

    session = auth.create_session(USER)
    token = session["token"] if isinstance(session, dict) else session
    result["session"] = {"resolves": auth.resolve(token) == USER,
                         "bad_token_rejected": auth.resolve("없는토큰") == ""}

    result["writes_through_product_api"] = seed_context(ecm)
    result["beyond_first_path"] = probe_profile_path(ecm)
    root = ecm.get_node(ROOT_NODE)
    result["context"] = {
        "root": getattr(root, "name_ko", None),
        "tenant": getattr(root, "tenant_id", None),
        "child": getattr(ecm.get_node(CHILD_NODE), "name_ko", None),
        #: 없는 노드는 «없음» 으로 — 빈 결과로 실패를 숨기지 않는지도 함께 본다.
        "absent_node": ecm.get_node("n_does_not_exist") is None,
    }

    ticket = auth.issue_sse_ticket(USER, token, tenant_id=TENANT,
                                   scope_node_id=ROOT_NODE, entity_mode="REAL")
    raw = ticket["ticket"] if isinstance(ticket, dict) else ticket
    first = auth.consume_sse_ticket(raw)
    result["ticket"] = {
        "first_consume_context": {k: first.get(k)
                                  for k in ("user_id", "tenant_id", "scope_node_id")},
        "second_consume_empty": auth.consume_sse_ticket(raw) == {},
        "unknown_ticket_empty": auth.consume_sse_ticket("없는티켓") == {},
    }

    #: ★★ 「DDL 0건」을 말하기 전에 **계측기가 살아 있었는지** 보인다. 기록이 0줄이어도
    #:   `ddl_statements` 는 똑같이 `[]` 를 돌려준다 — 그 둘을 구분하지 않으면 「아무것도
    #:   재지 않았음」이 「통제가 있음」으로 읽힌다.
    result["instrument"] = {
        "sql_statements_recorded": len(log),
        "recorder_catches_ddl": _recorder_positive_control(),
    }
    result["runtime_ddl_seen"] = ddl_statements(log)
    result["database_refuses_ddl"] = runtime_ddl_is_refused_by_the_database()
    return result


def _recorder_positive_control() -> bool:
    """대조군: **DDL 을 실제로 흘려 보내** 계측기가 잡는지 본다.

    DB 가 거절하더라도 기록은 실행 «전» 에 남으므로, 여기서 잡히면 계측기는 살아 있다."""
    probe: List[str] = []
    conn = RecordingFactory(postgres_factory(), probe)()
    try:
        conn.execute("CREATE TABLE instrument_probe_should_fail(a text)")
    except Exception:  # noqa: BLE001 — 거절이 기대값이고, 관심은 «기록» 이다
        pass
    finally:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        conn.close()
    return bool(ddl_statements(probe))


# ── 2단계: 동시 소비 (독립 연결) ────────────────────────────────────────
def phase_concurrent(workers: int = 4) -> Dict[str, Any]:
    auth, _ecm, _ = _stores()
    session = auth.create_session(USER)
    token = session["token"] if isinstance(session, dict) else session
    ticket = auth.issue_sse_ticket(USER, token, tenant_id=TENANT,
                                   scope_node_id=ROOT_NODE, entity_mode="REAL")
    raw = ticket["ticket"] if isinstance(ticket, dict) else ticket

    wins: List[Dict[str, str]] = []
    losers: List[str] = []
    lock = threading.Lock()
    gate = threading.Barrier(workers)

    def attempt() -> None:
        #: ★ 스레드마다 **자기 store 와 자기 연결**을 만든다.
        own, _e, _f = _stores()
        gate.wait()
        got = own.consume_sse_ticket(raw)
        #: ★★ **진 쪽이 살아 있었는지** 바로 확인한다. 제품은 예외를 삼켜 빈 사전을
        #:   돌려주므로, 「졌다」와 「연결이 터졌다」가 겉으로 똑같다. 그 둘을 같은
        #:   것으로 세면 경쟁 통제가 없어도 「정확히 하나」가 나온다.
        alive = own.resolve(token) == USER
        with lock:
            if got:
                wins.append(got)
            else:
                losers.append("졌음(연결 살아 있음)" if alive else "연결이 죽었음")

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    #: DB 쪽에서도 한 번 센다 — 응용의 반환값만 믿지 않는다.
    conn = postgres_factory()()
    try:
        consumed = conn.execute(
            "SELECT count(*) AS n FROM auth_sse_ticket "
            "WHERE token_hash=? AND consumed_at <> ''",
            (auth._ticket_hash(raw),)).fetchone()["n"]
    finally:
        conn.close()

    healthy_losses = sum(1 for x in losers if x.startswith("졌음"))
    naive = _naive_race_control(auth, token, workers)
    return {"workers": workers, "succeeded": len(wins),
            "naive_pattern_control": naive,
            "lost": len(losers), "losers": sorted(set(losers)),
            "losers_all_healthy": healthy_losses == len(losers),
            "db_rows_marked_consumed": consumed,
            "ok": len(wins) == 1 and consumed == 1 and healthy_losses == len(losers)}


def _naive_race_control(auth, session_token: str, workers: int) -> Dict[str, Any]:
    """★★ **음성 대조군**: 「1건」이 무엇 덕분인지 가른다.

    제품은 `UPDATE ... WHERE consumed_at=''` 한 문장으로 소비를 표시한다. 그 원자성이
    없다면 어땠을지를 같은 장벽·같은 스레드 수로 재연한다 — 여기서 **2건 이상**이 나와야
    「경쟁이 실제로 일어났고, 제품의 1건은 통제 덕분」이라고 말할 수 있다.
    여기서도 1건이 나온다면 내 시험이 경쟁을 못 만든 것이지 제품이 증명된 게 아니다.

    ⚠️ 제품 SQL 을 흉내 내는 **대조군 전용** 경로다. 제품 경로가 아니며, 격리된 로컬
      시험 DB 의 합성 티켓 한 장에만 닿는다."""
    ticket = auth.issue_sse_ticket(USER, session_token, tenant_id=TENANT,
                                   scope_node_id=ROOT_NODE, entity_mode="REAL")
    h = auth._ticket_hash(ticket["ticket"])
    wins = 0
    lock = threading.Lock()
    gate = threading.Barrier(workers)

    def naive() -> None:
        nonlocal wins
        conn = postgres_factory()()
        try:
            gate.wait()
            row = conn.execute(
                "SELECT consumed_at FROM auth_sse_ticket WHERE token_hash=?",
                (h,)).fetchone()
            if row is None or str(row["consumed_at"]) != "":
                return
            time.sleep(0.05)            # 「확인」과 「쓰기」 사이의 틈을 실제로 벌린다
            conn.execute("UPDATE auth_sse_ticket SET consumed_at=? WHERE token_hash=?",
                         ("2026-09-21T00:00:00", h))
            conn.commit()
            with lock:
                wins += 1
        finally:
            conn.close()

    threads = [threading.Thread(target=naive) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return {"succeeded": wins, "race_window_is_real": wins > 1}


# ── 3단계: 프로세스 재시작 뒤 대사 ──────────────────────────────────────
def phase_restart() -> Dict[str, Any]:
    """⚠️ **새 프로세스**에서 부른다. 같은 프로세스의 새 연결은 재시작 증거가 아니다."""
    auth, ecm, _ = _stores()
    root = ecm.get_node(ROOT_NODE)
    conn = ecm._connect()
    try:
        #: ⚠️ **티켓 건수로 지속성을 재지 않는다.** `issue_sse_ticket` 이 발급할 때마다
        #:   `expires_at < now` 인 표를 지운다(소비 여부와 무관). 티켓 수명은 30초이므로
        #:   프로세스를 다시 띄울 무렵에는 이미 쓸려 있다. 그것을 「사라졌다」로 읽으면
        #:   청소 동작을 지속성 결함으로 오인한다. 재시작 대사는 **수명이 긴 것**으로 한다.
        counts = {}
        for table in ("tenants", "enterprise_entities", "organization_nodes",
                      "auth_credential", "auth_session"):
            counts[table] = conn.execute(f'SELECT count(*) AS n FROM "{table}"'
                                         ).fetchone()["n"]
        tickets = conn.execute(
            "SELECT count(*) AS n FROM auth_sse_ticket").fetchone()["n"]
    finally:
        conn.close()

    #: ★ 새 프로세스에서 **처음부터 끝까지** 한 바퀴 더 돈다 — 살아남은 자료를 읽는
    #:   것과 「이 프로세스에서도 발급·소비가 된다」는 다른 주장이다.
    session = auth.create_session(USER)
    fresh = auth.issue_sse_ticket(USER, session["token"], tenant_id=TENANT,
                                  scope_node_id=CHILD_NODE, entity_mode="REAL")
    got = auth.consume_sse_ticket(fresh["ticket"])
    return {"login_still_works": auth.verify(USER, PASSWORD),
            "context_survived": getattr(root, "name_ko", None),
            "row_counts": counts,
            "tickets_before_fresh_cycle": tickets,
            "fresh_cycle_scope": got.get("scope_node_id"),
            "fresh_cycle_second_consume_empty": auth.consume_sse_ticket(fresh["ticket"]) == {}}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="실제 PG 제품 소비 (P03.2 / P03.3)")
    ap.add_argument("phase", choices=("login", "concurrent", "restart", "identity"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    if args.phase == "identity":
        result: Dict[str, Any] = identity()
    elif args.phase == "login":
        result = phase_login_and_tickets()
    elif args.phase == "concurrent":
        result = phase_concurrent(args.workers)
    else:
        result = phase_restart()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
