"""[§8.2 / §14 M3] 운영 준비 — 릴리스 체크리스트 · 롤백 · 변경 영향 분석.

## 세 가지를 한 모듈에 둔 이유

전부 **"이 릴리스를 운영에 둬도 되는가"** 라는 한 질문의 앞뒤다.
  · 체크리스트 — 지금 운영에 둘 준비가 됐는가 (§8.2 게이트 체인)
  · 롤백       — 아니었다면 무엇을 되돌릴 수 있는가
  · 영향 분석  — 기준·계약이 바뀌면 무엇이 흔들리는가 (§14 M3 「영향 분석」)

## 체크리스트는 §8.2 체인을 **재조회**한다

§8.2 는 7단계를 규정했고 이 저장소에는 그 대부분이 이미 있다. 체크리스트는 그것들을 다시
만들지 않고 **읽는다** — 같은 판정을 두 곳에서 계산하면 반드시 어긋난다.

| §8.2 단계 | 어디서 읽는가 |
|---|---|
| 코드/문서/스키마 검사 | 릴리스의 산출물 존재 여부(`release.json`) |
| 요구사항 추적성 | 릴리스의 추적성 산출물 |
| 핵심 업무 테스트 | `quality_telemetry` 게이트 결과 |
| 권한/데이터 계약 | `workspace_promotion.evaluate_gate` (§9.3 게이트 재사용) |
| 사용자 수용검수 | `quality_telemetry` 의 사람 판정 |
| Shadow Mode | `shadow_mode` 의 승격 이력 — **실운영 연계형에만 요구** |
| 릴리스 승인 | 승격 신청·오너 승인 기록 |

## 지키는 것

1. **확인하지 못한 것을 통과로 두지 않는다.** 기록이 없으면 `unverifiable` 이며 그것도
   "준비됨"이 아니다. 이 저장소의 관통 원칙이다.
2. **롤백이 하지 못한 일을 했다고 하지 않는다.** 이 시스템은 배포된 코드를 되돌리지 못한다.
   할 수 있는 것은 **사용 중단**과 **승격 철회**, 그리고 기록이다.
   응답에 그 한계를 적는다 — "롤백했다"는 말이 실제보다 크게 읽히면 아무도 후속 조치를 하지
   않는다.
3. **영향 분석은 승격 여부를 함께 본다.** "3개 노드 영향"과 "전사 승격된 앱 2개 영향"은
   완전히 다른 정보다. 전자만 주면 파급 규모를 오판한다.
4. **Shadow Mode 요구는 종류에 따라 다르다.** §8.2 가 "실운영 연계형 기능"에만 요구했으므로,
   연계가 없는 릴리스에까지 요구하면 게이트가 형식이 되고 사람들은 우회한다.

LLM 0콜.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 라이브러리 경로는 **단일 지점**에서 온다(`core/library_paths.py`). 여기서 다시 선언하면
#   게시(`factory_control`)·사용여부(`program_lifecycle`)와 어긋나 "존재하는 릴리스를 없다"고
#   판정하게 된다. 값이 아니라 함수를 쓰는 이유는 그 모듈 docstring 에 있다.
from core import library_paths
from core.paths import data_path

_DB_PATH = data_path("workspace.db")   # 워크스페이스와 같은 저장소(같은 수명주기)

#: §8.2 게이트 체인. 순서가 곧 진행 순서다.
GATE_STEPS = ("artifacts", "traceability", "tests", "permission_contract",
              "acceptance", "shadow_mode", "release_approval")

_DDL = """
CREATE TABLE IF NOT EXISTS release_rollbacks (
    rollback_id   TEXT PRIMARY KEY,
    release_id    TEXT NOT NULL,
    to_release_id TEXT DEFAULT '',
    reason        TEXT NOT NULL,
    actor         TEXT NOT NULL,
    revoked_promotion INTEGER NOT NULL DEFAULT 0,
    outcome       TEXT NOT NULL DEFAULT 'unknown',
    program_disabled INTEGER,
    disable_error TEXT NOT NULL DEFAULT '',
    promotion_error TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rollback_rel ON release_rollbacks(release_id, created_at DESC);
"""


class ReadinessError(ValueError):
    """검증/정책 위반 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_release(release_id: str) -> Optional[dict]:
    p = library_paths.release_json(release_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class ReleaseReadiness:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DB_PATH
        self._lock = threading.RLock()
        self._initialized_path = ""
        with self._connect():
            pass

    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        if self._initialized_path != self.db_path:
            conn.executescript(_DDL)
            # 과거 행은 성공 여부를 기록하지 않았다. 성공으로 소급 추정하지 않는다.
            columns = {row[1] for row in conn.execute('PRAGMA table_info(release_rollbacks)')}
            for name, ddl in (
                ('outcome', "TEXT NOT NULL DEFAULT 'unknown'"),
                ('program_disabled', 'INTEGER'),
                ('disable_error', "TEXT NOT NULL DEFAULT ''"),
                ('promotion_error', "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    conn.execute(f'ALTER TABLE release_rollbacks ADD COLUMN {name} {ddl}')
            conn.commit()
            self._initialized_path = self.db_path
        return conn

    # ── 체크리스트 (§8.2) ────────────────────────────────────────────────
    def checklist(self, release_id: str, project_id: str = "",
                  requires_live_integration: bool = False,
                  workspace_impl=None) -> dict:
        """§8.2 게이트 체인을 **재조회해** 운영 준비 상태를 판정한다.

        `requires_live_integration` 은 Shadow Mode 요구 여부다 — §8.2 가 "실운영 연계형
        기능"에만 요구했으므로 기본은 False 다. 모든 릴리스에 요구하면 게이트가 형식이 되고
        사람들은 우회한다."""
        rel = _load_release(release_id)
        steps: List[dict] = []

        def add(step: str, state: str, why: str, action: str = ""):
            steps.append({"step": step, "state": state, "why": why,
                          "suggested_action": action})

        if not rel:
            add("artifacts", "fail", f"라이브러리에 릴리스가 없습니다: {release_id}",
                "게시(release)를 먼저 수행하십시오.")
            return self._summarize(release_id, steps, project_id)

        # 1) 코드/문서/스키마 — 산출물이 실제로 있는가
        want = {"prd_summary": "요구사항", "architecture_summary": "아키텍처",
                "tech_spec_summary": "기술명세"}
        missing = [ko for k, ko in want.items() if not (rel.get(k) or "").strip()]
        code = any((rel.get(k) or "").strip()
                   for k in ("frontend_code_summary", "backend_code_summary"))
        if missing or not code:
            add("artifacts", "fail",
                (f"빠진 산출물: {', '.join(missing)}" if missing else "")
                + ("" if code else (" / " if missing else "") + "코드 산출물 없음"),
                "해당 단계를 완료한 뒤 다시 게시하십시오.")
        else:
            add("artifacts", "pass", "요구사항·아키텍처·기술명세·코드 산출물이 모두 있습니다.")

        # 2) 요구사항 추적성
        trace = (rel.get("traceability_summary") or rel.get("code_review_report_summary") or "")
        if not str(trace).strip():
            add("traceability", "unverifiable",
                "추적성 산출물이 릴리스에 없습니다.",
                "요구사항↔구현 링크(G1 추적성) 결과를 산출물에 포함하십시오 — "
                "없으면 '무엇을 구현했는지'를 증명할 수 없습니다.")
        else:
            add("traceability", "pass", "추적성 산출물이 있습니다.")

        # 3) 핵심 업무 테스트 + 5) 수용검수 — 같은 원천(품질 텔레메트리)에서 읽는다
        proj = (project_id or rel.get("project_id") or "").strip()
        if not proj:
            for st in ("tests", "acceptance"):
                add(st, "unverifiable", "품질 기록을 찾을 프로젝트를 알 수 없습니다.",
                    "project_id 를 지정하십시오.")
        else:
            try:
                from core import quality_telemetry as qt
                outcomes = qt.resolve_outcomes(qt.read_events(project=proj))
                if not outcomes:
                    add("tests", "unverifiable", f"'{proj}' 의 품질 게이트 기록이 없습니다.",
                        "게이트 기록 없이 운영에 두면 '검증했다'는 근거가 없습니다.")
                else:
                    failed = [o for o in outcomes
                              if str(o.get("pass_fail", "")).upper() == "FAIL"]
                    if failed:
                        add("tests", "fail",
                            f"실패한 게이트 {len(failed)}/{len(outcomes)}건.",
                            "실패 원인을 해소하십시오.")
                    else:
                        add("tests", "pass", f"게이트 {len(outcomes)}건 전부 통과.")
                # 수용검수 — 사람 판정. "묻지 않은 것"을 승인으로 치지 않는다(D-015).
                #   ⚠️ 필드명은 `human_acceptance` 다. `human_decision` 처럼 없는 키를 보면
                #     조용히 0건이 되어 "수용검수 없음"으로 오판한다(실제로 그렇게 썼다가 고침).
                accepted = [o for o in outcomes
                            if o.get("human_acceptance") == qt.HUMAN_ACCEPTED]
                asked = [o for o in outcomes
                         if o.get("human_acceptance") in (qt.HUMAN_ACCEPTED,
                                                          qt.HUMAN_REVISION_REQUESTED)]
                if not asked:
                    add("acceptance", "unverifiable",
                        "사람 판정 기록이 없습니다(승인이 아니라 **묻지 않은 것**입니다).",
                        "수용검수를 수행하십시오.")
                elif not accepted:
                    add("acceptance", "fail", "수용검수에서 수정 요청만 있었습니다.",
                        "수정 후 다시 수용검수를 받으십시오.")
                else:
                    add("acceptance", "pass", f"수용검수 승인 {len(accepted)}건.")
            except Exception as e:
                for st in ("tests", "acceptance"):
                    add(st, "unverifiable", f"품질 기록을 읽을 수 없습니다: {e}")

        # 4) 권한/데이터 계약 — §9.3 게이트를 그대로 재사용한다(두 곳에서 계산하지 않는다)
        try:
            from core.workspace_promotion import workspace as _ws
            ws = workspace_impl or _ws
            g = ws.evaluate_gate(release_id, "enterprise", project_id=proj)
            sub = {c["check"]: c for c in g["checks"]}
            pc = [sub.get(k) for k in ("data_contract", "security") if sub.get(k)]
            bad = [c for c in pc if c["state"] == "fail"]
            unk = [c for c in pc if c["state"] == "unverifiable"]
            if bad:
                add("permission_contract", "fail",
                    "; ".join(c["why"] for c in bad),
                    "; ".join(c.get("suggested_action", "") for c in bad))
            elif unk:
                add("permission_contract", "unverifiable",
                    "; ".join(c["why"] for c in unk),
                    "; ".join(c.get("suggested_action", "") for c in unk))
            else:
                add("permission_contract", "pass", "데이터 계약·보안 검사를 통과했습니다.")
        except Exception as e:
            add("permission_contract", "unverifiable", f"계약·보안 검사를 읽을 수 없습니다: {e}")

        # 6) Shadow Mode — **실운영 연계형에만** 요구(§8.2)
        if not requires_live_integration:
            add("shadow_mode", "not_required",
                "실운영 연계형 기능이 아니어서 Shadow Mode 를 요구하지 않습니다(§8.2).")
        else:
            try:
                from core.shadow_mode import shadow_mode
                runs = [r for r in shadow_mode.list_runs()
                        if release_id in (r.get("candidate_ref", ""),
                                          r.get("baseline_ref", ""))
                        or release_id == r.get("name")]
                promoted = [r for r in runs if r.get("promoted")]
                if promoted:
                    add("shadow_mode", "pass",
                        f"Shadow Mode 승격 이력 {len(promoted)}건(범위 제한).")
                elif runs:
                    add("shadow_mode", "fail",
                        f"Shadow run {len(runs)}건이 있으나 승격된 것이 없습니다.",
                        "병렬 검증 결과를 검토·승격한 뒤 릴리스하십시오.")
                else:
                    add("shadow_mode", "unverifiable",
                        "실운영 연계형인데 Shadow run 기록이 없습니다.",
                        "같은 입력으로 현행·후보를 병렬 실행해 비교하십시오(§7.3).")
            except Exception as e:
                add("shadow_mode", "unverifiable", f"Shadow 기록을 읽을 수 없습니다: {e}")

        # 7) 릴리스 승인 — 승격 신청·오너 승인
        try:
            from core.workspace_promotion import workspace as _ws2
            ws2 = workspace_impl or _ws2
            pr = ws2.get_promotion(release_id)
            if pr and pr.get("status") == "promoted":
                add("release_approval", "pass",
                    f"전사 승격 완료 · {pr.get('promoted_by', '')}")
            elif pr and pr.get("data_owner_approved_by"):
                add("release_approval", "pass",
                    f"데이터 오너 승인 · {pr['data_owner_approved_by']}")
            elif pr:
                add("release_approval", "fail",
                    f"승격 신청 상태: {pr.get('status')}. 승인이 없습니다.",
                    "데이터 오너 승인을 받으십시오.")
            else:
                add("release_approval", "unverifiable",
                    "릴리스 승인 기록이 없습니다.",
                    "부서 내 사용만이면 전사 승격 신청은 필요 없으나, 운영 배치에는 승인 근거가 "
                    "있어야 합니다.")
        except Exception as e:
            add("release_approval", "unverifiable", f"승인 기록을 읽을 수 없습니다: {e}")

        return self._summarize(release_id, steps, proj)

    def _summarize(self, release_id: str, steps: List[dict], project_id: str) -> dict:
        # ★ `GATE_STEPS` 순서로 정렬한다. §8.2 의 체인은 **진행 순서**라 의미가 있는데,
        #   검사 코드는 같은 원천을 쓰는 것끼리 묶여 있어(테스트·수용검수가 한 블록) 추가 순서가
        #   체인 순서와 어긋난다. 화면에 ⑤가 ④보다 먼저 나오면 체인이 잘못된 것처럼 보인다.
        #   상수를 선언만 하고 쓰지 않으면 그 상수는 없는 것과 같다(실측으로 확인).
        order = {s: i for i, s in enumerate(GATE_STEPS)}
        steps = sorted(steps, key=lambda s: order.get(s["step"], len(order)))
        failed = [s["step"] for s in steps if s["state"] == "fail"]
        unver = [s["step"] for s in steps if s["state"] == "unverifiable"]
        return {
            "release_id": release_id, "project_id": project_id,
            "steps": steps, "failed": failed, "unverifiable": unver,
            # ★ unverifiable 도 "준비됨"이 아니다.
            "operations_ready": not failed and not unver,
            "note": ("`unverifiable` 은 통과가 아니라 **확인하지 못한 것**이며 운영 준비로 "
                     "인정되지 않습니다. `not_required` 는 §8.2 가 해당 종류에 요구하지 않은 "
                     "단계입니다."),
        }

    # ── 롤백 ─────────────────────────────────────────────────────────────
    def rollback(self, release_id: str, actor: str, reason: str,
                 to_release_id: str = "", workspace_impl=None,
                 lifecycle_impl=None, disable_program: bool = True) -> dict:
        """운영에서 내린다. **이 시스템이 할 수 있는 것만 한다.**

        [사용자 결정 2026-07-30] 배포된 코드를 되돌리지는 못하지만, **사용을 막을 수는 있다.**
        그래서 롤백은 이제 프로그램을 `disabled` 로 내린다(삭제가 아니다 — 기록은 보존된다).
        지우지 않는 이유: 다른 사용자가 이 프로그램을 근거로 남긴 기록이 고아가 된다.

        수행하는 것: ① 사용 중단 ② 전사 승격 철회 ③ 되돌릴 대상 릴리스를 대체본으로 지정
        ④ 사유·행위자 기록.
        ⚠️ 여전히 못 하는 것: 이미 실행 중인 인스턴스의 되돌림, 외부 배포본 회수."""
        if not (actor or "").strip():
            raise ReadinessError("actor 는 필수입니다 — 누가 내렸는지 없으면 근거가 없습니다.")
        if not (reason or "").strip():
            raise ReadinessError(
                "reason 은 필수입니다 — 사유 없는 롤백은 같은 문제를 반복하게 만듭니다.")
        if not release_id or any(c in release_id for c in ('/', '\\', '..')):
            raise ReadinessError('유효한 릴리스를 선택하십시오.')
        if not _load_release(release_id):
            raise ReadinessError('운영에서 내릴 릴리스를 찾거나 읽을 수 없습니다.')
        if to_release_id and (any(c in to_release_id for c in ('/', '\\', '..'))
                              or not _load_release(to_release_id)):
            raise ReadinessError(f"되돌릴 대상 릴리스가 없습니다: {to_release_id}")
        if to_release_id == release_id:
            raise ReadinessError('같은 릴리스를 대체본으로 지정할 수 없습니다.')

        rid = f"rb_{uuid.uuid4().hex[:12]}"
        now = _now()
        # 기록 저장소가 처음부터 불통이면 상태 변경을 시작하지 않는다.
        # 중간에 프로세스가 멈추면 in_progress가 남으며 완료로 보이지 않는다.
        with self._lock, self._connect() as conn:
            conn.execute(
                'INSERT INTO release_rollbacks(rollback_id,release_id,to_release_id,reason,'
                'actor,created_at,outcome) VALUES(?,?,?,?,?,?,?)',
                (rid, release_id, to_release_id, reason, actor, now, 'in_progress'))

        # 사용 중단을 먼저 한다. 이것이 실패하면 승격 상태까지 바꾸지 않는다.
        disabled, disable_error = False, ""
        if disable_program:
            try:
                from core.program_lifecycle import program_lifecycle as _pl
                pl = lifecycle_impl or _pl
                current = pl.get_status(release_id)
                # 재시도로 기존 중단 사유·지문·대체본을 지우지 않는다.
                if current.get('status') != 'disabled' or (
                    to_release_id and current.get('replacement_release_id') != to_release_id
                ):
                    pl.disable(release_id, actor, f"롤백: {reason}",
                               replacement_release_id=to_release_id,
                               acknowledge_dependents=True)
                if pl.get_status(release_id).get('status') != 'disabled':
                    raise RuntimeError('사용 중단 상태가 저장되지 않았습니다.')
                disabled = True
            except Exception as e:
                disable_error = str(e)
                print(f"⚠️ [Readiness] 프로그램 사용 중단 실패: {e}")

        revoked, promotion_error = False, ''
        if not disable_error:
            try:
                from core.workspace_promotion import workspace as _ws
                ws = workspace_impl or _ws
                pr = ws.get_promotion(release_id)
                if pr and pr.get('status') == 'promoted':
                    ws.revoke_promotion(release_id, actor, f'롤백: {reason}')
                    if (ws.get_promotion(release_id) or {}).get('status') != 'revoked':
                        raise RuntimeError('전사 승격 철회 상태가 저장되지 않았습니다.')
                    revoked = True
            except Exception as e:
                promotion_error = str(e)
                print(f'⚠️ [Readiness] 전사 승격 철회 확인 실패: {e}')

        outcome = ('failed' if disable_error else
                   ('partial' if disabled else 'failed') if promotion_error else 'complete')
        message = ('운영에서 내렸습니다. 원본 코드·데이터·이력은 보관됩니다.'
                   if disabled and outcome == 'complete' else
                   '사용은 중단됐지만 전사 승격 철회를 확인하지 못했습니다. 다시 시도하십시오.'
                   if outcome == 'partial' else
                   '사용 중단을 확인하지 못했습니다. 현재 상태를 확인한 뒤 다시 시도하십시오.'
                   if disable_error else
                   '전사 승격 철회를 확인하지 못했습니다. 다시 시도하십시오.'
                   if promotion_error else '사용 중단 없이 승격 상태만 처리했습니다.')
        out = {
            "rollback_id": rid, "release_id": release_id, "to_release_id": to_release_id,
            "revoked_promotion": revoked, "actor": actor, "reason": reason, "created_at": now,
            "program_disabled": disabled, "disable_error": disable_error,
            'promotion_error': promotion_error, 'outcome': outcome, 'message': message,
            'history_recorded': True,
            "limitation": (
                ("전사 승격 철회를 확인했습니다. " if revoked else "")
                + "프로그램은 **삭제하지 않았습니다** — 다른 사용자가 남긴 기록이 "
                  "고아가 되기 때문입니다. 이 시스템은 **이미 배포된 코드 자체를 되돌리지는 "
                  "못합니다**(실행 중 인스턴스·외부 배포본). 그 되돌림은 별도로 수행하고 "
                  "결과를 확인하십시오."),
        }
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    'UPDATE release_rollbacks SET revoked_promotion=?,outcome=?,'
                    'program_disabled=?,disable_error=?,promotion_error=? WHERE rollback_id=?',
                    (int(revoked), outcome, int(disabled), disable_error, promotion_error, rid))
        except sqlite3.Error:
            # 이미 내린 앱을 다시 열지 않는다. 최초 요청 기록을 남기고 불완전 결과를 알린다.
            out.update(outcome='partial' if disabled or revoked else 'failed',
                       history_recorded=False,
                       message='처리 결과의 이력 저장을 확인하지 못했습니다. 상태와 이력을 재확인하십시오.')
        return out

    def rollback_history(self, release_id: str = "") -> List[dict]:
        sql, params = "SELECT * FROM release_rollbacks", []
        if release_id:
            sql += " WHERE release_id=?"
            params.append(release_id)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC",
                                                  tuple(params)).fetchall()]

    # ── 변경 영향 분석 (§14 M3) ──────────────────────────────────────────
    def change_impact(self, node_type: str, node_id: str, lineage=None,
                      workspace_impl=None) -> dict:
        """기준정보·계약·자산이 바뀌면 **무엇이 흔들리는가.**

        ★ 계보 결과에 **승격 여부를 얹는다.** "3개 노드 영향"과 "전사 승격된 앱 2개 영향"은
          완전히 다른 정보고, 전자만 주면 파급 규모를 오판한다."""
        from core.data_lineage import data_lineage
        lin = lineage or data_lineage
        imp = lin.impact_of(node_type, node_id, direction="downstream")

        from core.workspace_promotion import workspace as _ws
        ws = workspace_impl or _ws
        releases, projects, enterprise = [], [], []
        for n in imp["impacted"]:
            if n["node_type"] == "release":
                pr = None
                try:
                    pr = ws.get_promotion(n["node_id"])
                except Exception:
                    pass
                item = {"release_id": n["node_id"], "depth": n["depth"],
                        "promotion_status": (pr or {}).get("status", ""),
                        "is_enterprise": bool(pr and pr.get("status") == "promoted")}
                releases.append(item)
                if item["is_enterprise"]:
                    enterprise.append(item)
            elif n["node_type"] == "project":
                projects.append({"project_id": n["node_id"], "depth": n["depth"]})

        return {
            "root": imp["root"], "impacted_count": imp["impacted_count"],
            "impacted": imp["impacted"],
            "releases": releases, "projects": projects,
            "enterprise_releases": enterprise,
            "blast_radius": ("enterprise" if enterprise else
                             ("department" if releases or projects else "none")),
            "truncated": imp["truncated"],
            "limitation": (imp["limitation"] + " 또한 승격되지 않은 릴리스도 부서 내에서 "
                           "쓰이고 있을 수 있습니다 — 승격 여부는 **파급 범위**의 지표이지 "
                           "사용 여부의 지표가 아닙니다."),
        }


release_readiness = ReleaseReadiness()
