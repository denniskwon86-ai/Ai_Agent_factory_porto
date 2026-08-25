# -*- coding: utf-8 -*-
"""★★★ [M0] **로컬 시연 서버** — 12분 여정을 이 기계에서 처음부터 걸을 수 있게 한다.

## 왜 필요한가

운영 `data/` 에는 키트 인스턴스도, 인증판도, 온톨로지 관계도 **0건**이다. 그래서 지금
이 저장소를 그대로 띄우면 시연을 시작할 수 없다 — 화면은 뜨지만 고를 것이 없다.

## ⚠️⚠️ 운영 `data/` 에 심지 않는다

이 저장소의 규칙이다(`scripts/pilot_demo_seed.py` 머리말): **시연 데이터를 운영
저장소에 심으면 그 순간 「실제 데이터」와 구분되지 않는다.**

★ 그래서 별도 뿌리(`demo_data/`)에 심고, 앱의 저장소 경로를 그쪽으로 돌려 띄운다.
  운영 `data/` 는 열지도 않는다 — 아래에서 직접 막는다.

## 무엇을 심는가

    조직        본사 → 제련공장(상위→하위 상속을 볼 수 있게)
    사용자      hikwon@lsmnm.com(시스템 관리자) · runner@afs.invalid(실행자)
    키트        KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0 — **정본 파일**에서 읽는다
    인증판      필수 7종
    온톨로지    계약 + 관계 3건(제안→상신→승인, **실제 원장 사건**으로)
    기준선      배분·인식규칙·기준 인식일 봉인

## ⚠️ 심지 **않는** 것 — 계산 능력 실행 승인

사람이 화면에서 눌러야 한다(사용자 결정 2026-08-22). 그래서 이 스크립트가 심으면
「승인 화면이 실제로 도는가」를 확인할 수 없다 — 처음부터 승인된 상태로 시작하면
그 화면은 한 번도 안 눌린 채 시연이 끝난다.

사용:
    venv/Scripts/python.exe scripts/run_local_demo.py            # 있으면 그대로, 없으면 심고 기동
    venv/Scripts/python.exe scripts/run_local_demo.py --reset    # 비우고 다시 심는다
    venv/Scripts/python.exe scripts/run_local_demo.py --seed-only
    venv/Scripts/python.exe scripts/run_local_demo.py --port 8080

LLM 호출: 0건.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: 시연 뿌리. ⚠️ 운영 `data/` 와 **다른 디렉터리**여야 한다.
DEMO_ROOT = os.path.join(ROOT, "demo_data")
OPERATIONAL = os.path.join(ROOT, "data")

#: ★★★ [2026-08-23] **파종 대상 뿌리.** 기본은 시연 뿌리다.
#:
#: `scripts/seed_starter_data.py` 가 이 값을 운영 뿌리로 바꿔 **같은 파종 코드**를 쓴다.
#: 파종을 두 벌로 만들면 두 곳이 서로 다른 것을 심게 되고, 「시연에서는 되는데 실제로
#: 띄우면 안 된다」가 다시 생긴다 — 이 저장소가 오버레이 목록에서 방금 겪은 그 유형이다.
#: ⚠️ 이 값을 운영으로 바꾸는 쪽은 **봉인(`_seal_operational_data`)을 걸지 않는다.**
#:   봉인은 「시연이 운영을 건드리지 않는다」를 지키는 장치이고, 의도적으로 운영에 심는
#:   경로에서는 그것이 자기 자신을 막는다.
TARGET_ROOT = DEMO_ROOT

#: ★ 파종에 쓸 테넌트. 비우면 **정본 CSV 의 값**을 쓰고 `config` 를 거기에 맞춘다(시연).
#:   값을 주면 **자료를 그 테넌트로** 심는다 — 설치본의 설정을 건드리지 않는다(운영).
TENANT_OVERRIDE = ""

#: ★★★ [2026-08-24] 조직을 **만들지 않는다**(운영 파종용).
#:
#: ⚠️ `_org()` 는 `<뿌리>/org.db` 에 두 단짜리 조직을 세우고 **싱글턴을 그쪽으로 돌린다.**
#:   시연 뿌리에서는 맞지만, 운영에서는 앱이 읽는 `data/master/master.db` 를 무시한
#:   별도 파일이 생기고 — 더 나쁘게 — **소유권 결속이 그 임시 조직의 부서(`smelting`)를
#:   가리킨다.** 앱에는 그 부서가 없으므로 해석기가 「부서가 없거나 폐지됐습니다」로 막는다.
#: ★ 운영에는 이미 조직이 있다. 그것을 쓴다.
SKIP_ORG = False


def _rebase_days() -> int:
    """조각의 업무 날짜를 **몇 일 옮길 것인가.** 한 번 정하면 뿌리에 고정된다.

    ## ⚠️⚠️ 매번 새로 계산하면 사슬이 끊긴다

    관계는 `shipment:SHP-000001 → inventory-snapshot:STK-20260823-…` 처럼 **날짜가
    박힌 객체 id** 를 가리킨다. 보충 실행(`--top-up`)이 다른 오프셋을 쓰면 새로 심은
    판의 id 가 어제 심은 관계가 가리키는 id 와 어긋나고, 경로는 조용히 끊긴다.
    ★ 그래서 처음 심을 때 정해 `<뿌리>/slice_rebase.json` 에 적고, 이후로는 읽는다.
    """
    import json as _json
    from datetime import date as _date
    from core import demo_vertical_slice as _dv

    path = os.path.join(TARGET_ROOT, "slice_rebase.json")
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            return int(_json.load(fh)["days"])
    days = max(0, (_date.today() - _date.fromisoformat(_dv.AS_OF[:10])).days)
    os.makedirs(TARGET_ROOT, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        _json.dump({"days": days, "slice_as_of": _dv.AS_OF,
                    "pinned_on": _date.today().isoformat(),
                    "why": "자료의 업무 날짜를 설치일 기준으로 옮긴 양(정본 CSV 는 그대로)"},
                   fh, ensure_ascii=False, indent=1)
    return days


def _slice(scope: str = "plant-afs-smelting-01"):
    """시연 조각 — **업무 날짜를 설치일 기준으로 옮겨서** 돌려준다.

    ★★★ `dv.build_slice` 를 직접 부르지 않는다. 옮기지 않은 조각으로 심으면 계획행이
      전부 과거가 되어 생산가능량이 비고, 다섯 관문이 전부 READY 인데 계산만
      `BLOCKED` 로 답한다(2026-08-24 실측 — 원인을 찾는 데 한나절 걸렸다)."""
    from core import demo_vertical_slice as _dv

    moved, _counts = _dv.rebase(_dv.build_slice(scope_node_id=scope), _rebase_days())
    return moved

def _seal_operational_data() -> None:
    """**운영 `data/` 를 열 수 없게 만든다.** 머리말의 약속을 코드로 만든다.

    ## ⚠️⚠️ 왜 필요한가 — 약속만 있고 차단이 없었다(2026-08-23 실측)

    `_point_stores_at_demo()` 는 싱글턴 **5개**의 `db_path` 만 갈아끼운다. 그런데 앱이
    실제로 여는 저장소는 그보다 훨씬 많다. 열린 파일을 런타임에서 세어 보니 **10개가
    운영 `data/` 로 샜다** — `auth.db`(로그인 세션!) `workspace.db` `planning.db`
    `enterprise_context.db` `master/master.db` 등.

    ★ 그런데 이 스크립트는 화면에 「운영 data/ 는 열지 않습니다」라고 **찍고 있었다.**
      머리말도 「아래에서 직접 막는다」고 적었다. 막는 코드는 없었다.
      주장하는 통제는 통제가 아니다 — 그것이 이 저장소가 반복해서 잡아 온 결함이다.

    ## 두 겹으로 막는다

    ① `core.paths.DATA_DIR` 를 시연 뿌리로 돌린다 — 저장소 38곳이 여기서 경로를 얻으므로
       **한 곳을 고치면 앞으로 생길 저장소도 따라온다.** 열거 방식은 새 저장소가 생길 때
       조용히 샌다.
    ② 그래도 절대경로를 박아 둔 곳이 있을 수 있다. `sqlite3.connect` 에 차단기를 달아
       운영 뿌리를 열려는 순간 **터뜨린다.** 조용히 여는 것보다 죽는 편이 낫다.

    ⚠️ ①만으로 끝내지 않는 이유: ① 이 통하는지 확인할 방법이 ② 밖에 없다. 통제가 자기가
      막을 것에 기대면 안 된다.
    """
    import sqlite3

    import core.paths as paths

    paths.DATA_DIR = DEMO_ROOT
    op = os.path.abspath(OPERATIONAL) + os.sep

    _real_connect = sqlite3.connect

    def guarded(database, *a, **k):
        raw = str(database)
        if raw != ":memory:" and not raw.startswith("file::memory:"):
            probe = os.path.abspath(raw.replace("file:", "", 1).split("?")[0])
            if probe.startswith(op):
                raise SystemExit(
                    "\n운영 저장소를 열려고 했습니다 — 멈춥니다."
                    f"\n  {probe}"
                    f"\n  시연은 {DEMO_ROOT} 만 씁니다. "
                    "이 경로를 쓰는 저장소를 찾아 돌리십시오.")
        return _real_connect(database, *a, **k)

    sqlite3.connect = guarded

    #: ★★ DB 만 막으면 반쪽이다 — `interaction_log.jsonl`·`company_profile.json` 처럼
    #:   **평범한 파일**로 운영 뿌리에 쓰는 곳이 있었다(`core/persona_learner.py`).
    #:   ⚠️ 읽기는 막지 않는다. 운영 뿌리의 정본을 **참고**하는 것은 오염이 아니고,
    #:     막으면 「없는 것」과 「못 읽은 것」이 뒤섞인다.
    import builtins

    _real_open = builtins.open

    def guarded_open(file, mode="r", *a, **k):
        if any(c in str(mode) for c in ("w", "a", "x", "+")):
            try:
                probe = os.path.abspath(os.fspath(file))
            except TypeError:
                probe = ""          # 파일 서술자(int) — 경로가 아니므로 판정 대상이 아니다
            if probe.startswith(op):
                raise SystemExit(
                    "\n운영 뿌리에 파일을 쓰려고 했습니다 — 멈춥니다."
                    f"\n  {probe}"
                    f"\n  시연은 {DEMO_ROOT} 만 씁니다.")
        return _real_open(file, mode, *a, **k)

    builtins.open = guarded_open


USER_ADMIN = "hikwon@lsmnm.com"          # ★ 승인된 실측 계정 하나
#: ★ 제안자와 승인자는 달라야 한다(자기 승인 금지). 합성 원장 행위자를 쓴다.
USER_PROPOSER = "proposer@afs.invalid"
USER_RUNNER = "runner@afs.invalid"
DEPT_HQ, DEPT_PLANT = "hq", "smelting"

#: 시연 회사의 **사람이 읽는 이름**. ⚠️ 화면에서 지어내지 않고 저장소에 심는다.
DEMO_COMPANY_NAME = "LS MnM"
DEMO_COMPANY_LEGAL = "LS엠엔엠 주식회사"

def chain_from_slice(sl) -> tuple:
    """관계 사슬을 **정본 자료에서** 뽑는다.

    ## ⚠️⚠️ [2026-08-24 실측] 종전 사슬은 **지어낸 ID** 였다

        (("shipment","SHP-001"), ("inventory-snapshot","INV-001"),
         ("production-plan","PLAN-001"), ("sales-order","SO-001"))

    색인(`object_scope_index`)에 실제로 있는 것은 `SHP-000001`·`STK-20260531-…`·
    `MPS-0003001`·`SO-001666-10` 이고 **타입 이름도 다르다**(`production-plan-line`·
    `sales-line`). 즉 이 사슬의 끝점은 제품 해석기로 물으면 전부 `NOT_FOUND` 다.

    ★ 그런데 시연은 잘 돌았다 — 시연 스크립트가 **무엇을 묻든 「찾았다」고 답하는 스텁
      해석기**를 심었기 때문이다. 그 위에서는 어떤 ID 를 넣어도 경로가 나온다.
      화면은 초록인데 제품 경로로는 한 줄도 성립하지 않는 상태였다.

    ⚠️ 스텁 위의 초록을 «된다» 로 세지 않는다. 사슬은 **자료가 실제로 잇는 것**이어야 한다:

        선적 → (발주로 자재를 찾아) 그 자재의 재고 → 그 자재를 쓰는 생산계획 → 그 제품의 판매
    """
    def first(key, col):
        rows, cols = sl[key]
        for r in rows:
            v = str(r.get(col, "") or "").strip()
            if v:
                return v
        raise ValueError(f"{key}.{col} 가 비어 있습니다 — 사슬을 만들 수 없습니다.")

    #: ⚠️ 재고는 **RAW**(원료) 판을 고른다. WIP 는 이미 투입된 것이라 「도착 지연이 재고를
    #:   줄인다」는 이야기의 대상이 아니다.
    inv_rows, inv_cols = sl["INV-01"]
    raw = [r for r in inv_rows if "RAW" in str(r.get("snapshot_id", ""))]
    inv_id = str((raw or inv_rows)[0].get("snapshot_id"))

    return (("shipment", first("LOG-02", "shipment_id"),
             "inventory-snapshot", inv_id),
            ("inventory-snapshot", inv_id,
             "production-plan-line", first("MFG-01", "plan_line_id")),
            ("production-plan-line", first("MFG-01", "plan_line_id"),
             "sales-line", first("SLS-01", "sales_line_id")))


#: ★★★ [2026-08-23 실측] **콘솔이 cp949 면 기동이 죽는다.**
#:
#: ⚠️⚠️ 시연 서버를 IDE·러너에서 띄우면 stdout 이 시스템 코드페이지(cp949)로 열린다.
#:   그러면 `▸`·`✓` 같은 글자에서 `UnicodeEncodeError` 가 나고 **기동 자체가 실패한다** —
#:   그런데 그 시점에 이미 「시연 뿌리」·「data/ 를 열지 않습니다」까지 찍혀 있어서,
#:   로그만 보면 정상 기동한 것처럼 보인다. 조용한 실패가 아니라 **시끄러운 오해**다.
#: ★ 여기서 한 번 고정한다. 환경 변수에 기대지 않는다 — 부르는 쪽마다 다르다.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def rematerialize_index(tenant: str, scope: str) -> int:
    """색인을 **다시 세운다** — 소유권 결속이 생긴 뒤에는 필수다.

    ## ⚠️⚠️ [2026-08-24 실측] 결속만 만들면 색인은 그것을 모른다

    색인 줄은 **인증 시점의 소유권을 봉인**한다(`scope_index.write_conn`). 결속이 없던
    때에 인증된 줄은 `owner_binding_id=""` 로 남고, 나중에 결속을 만들어도 해석기가
    거부한다:

        「이 색인은 소유권 결속이 없던 때에 만들어졌는데 지금은 결속이 있습니다 —
         재물질화가 필요합니다(색인이 모르는 승인을 권한으로 쓰지 않습니다)」

    ★ 그 거부는 **옳다.** 색인이 모르는 승인을 권한으로 쓰면, 나중에 결속을 바꿔치기해
      과거 판정을 뒤집을 수 있다. 그러니 우회하지 말고 **다시 세운다.**
    ★ 인증 때와 **같은 경로**(`plan` → `write_conn`)를 쓴다 — 재물질화용 별도 코드를
      만들면 두 경로가 갈라지고, 갈라진 쪽은 언젠가 한쪽만 고쳐진다.
    """
    from core.data_preparation import scope_index
    from core.data_preparation.store import data_preparation_store as store

    done = 0
    with store.transaction() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM dataset_snapshots WHERE tenant_id=? AND scope_node_id=? "
            "AND state IN ('CERTIFIED','DEMO_CERTIFIED')", (tenant, scope))]
        for row in rows:
            try:
                payload = scope_index.plan(row)
            except Exception:
                continue                     # 색인 대상이 아닌 계약키
            if not payload:
                continue
            scope_index.write_conn(conn, payload, str(row.get("certified_at") or ""))
            done += 1
    return done


def dept_owning(scope: str) -> str:
    """이 범위를 가진 **실재하는 부서**를 찾는다.

    ⚠️⚠️ [2026-08-24 실측] 부서 코드를 상수로 박으면(`DEPT_PLANT="smelting"`) 그 코드가
      없는 설치본에서 결속이 죽는다:

          「결속이 가리키는 부서 «smelting» 가 없거나 폐지됐습니다 — 색인이 있어도 막습니다」

      시연 뿌리에는 `smelting` 을 직접 만들지만, 운영 조직에는 이미 다른 부서 체계가 있고
      시연 자료의 자리는 `demo_smelting` 이다. **범위가 정본이고 부서 코드는 설치본마다
      다르다** — 범위로 찾는다."""
    from core.org_directory import org_directory

    for d in org_directory.list_departments():
        if str(d.get("scope_node_id") or "").strip() == scope:
            return str(d.get("dept_id"))
    #: ⚠️ 못 찾으면 상수로 되돌아가지 않는다 — 없는 부서를 적으면 결속이 만들어지고
    #:   나중에 «색인이 있어도 막히는» 상태가 된다. 원인을 그 자리에서 말한다.
    raise ValueError(
        f"범위 {scope} 를 가진 부서가 조직도에 없습니다 — 소유권 결속을 만들 수 없습니다. "
        f"먼저 그 범위를 가진 부서를 만드십시오.")


def seed_ownership(tenant: str, scope: str, keys) -> int:
    """데이터셋 **소유권 결속**을 심는다. 없으면 객체가 전부 `UNBOUND` 다.

    ## ⚠️⚠️ [2026-08-24 실측] 이것이 없어서 경로 계산이 성립하지 않았다

    제품 해석기(`_resolve_dataset`)에 실제 업무 ID 를 물어도 답이 **`UNBOUND`** 였다 —
    `dataset_ownership_bindings` 가 **0건**이었기 때문이다. 색인의 `owner_dept_id`·
    `owner_binding_id` 도 전부 빈 값이었다.

    ★ 시연은 스텁 해석기 덕에 초록이었으므로 이 결손이 드러나지 않았다.

    ## 두 단계다 — 하나만 하면 안 된다

        approve()   원장에 **승인 사건**을 남긴다(행위자 권한도 여기서 확인한다)
        declare()   그 사건 id 를 근거로 정본에 등록한다

    ⚠️ `declare()` 만 부르면 「승인됐다고 스스로 적은 결속」이 된다 — 이 모듈 머리말이
      1차 구현의 결함으로 기록해 둔 바로 그 자기진술이다.
    ★ 같은 지문의 재적용은 멱등이다(모듈이 보장). 두 번 돌려도 중첩되지 않는다.
    """
    from core.data_preparation import ownership_binding as ob
    from core.data_preparation import store as dp

    owner = dept_owning(scope)
    made = 0
    for key in keys:
        try:
            ap = ob.approve(
                tenant_id=tenant, entity_mode="REAL", dataset_contract_key=key,
                scope_node_id=scope, owner_dept_id=owner, actor_id=USER_ADMIN,
                evidence_ref=("정본 스타터 키트 시작 자료 — 제련공장이 이 데이터의 "
                              "소유 부서임을 확인함"),
                purpose="시작 자료 파종")
            with dp.data_preparation_store.transaction() as conn:
                ob.declare(
                    conn, tenant_id=tenant, entity_mode="REAL",
                    dataset_contract_key=key, scope_node_id=scope,
                    owner_dept_id=owner, approved_by=USER_ADMIN,
                    evidence_ref=("정본 스타터 키트 시작 자료 — 제련공장이 이 데이터의 "
                                  "소유 부서임을 확인함"),
                    approval_event_id=ap["approval_event_id"],
                    effective_from=ap["effective_from"])
            made += 1
        except Exception as e:  # noqa: BLE001
            #: ⚠️ 하나가 실패해도 나머지를 심는다 — 다만 **조용히 넘기지 않는다.**
            print(f"    ⚠️ {key}: {type(e).__name__} {str(e)[:70]}")
    return made


def _now_iso() -> str:
    """지금(UTC). ★ 인증·발효처럼 **시스템 시각**이 필요한 곳에만 쓴다."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _chain_text(chain) -> str:
    """사슬을 한 줄로 — 심은 것이 «무엇인지» 를 로그에 남긴다."""
    parts = [f"{chain[0][0]}:{chain[0][1]}"]
    for _s_t, _s_i, o_t, o_i in chain:
        parts.append(f"{o_t}:{o_i}")
    return " → ".join(parts)


def say(msg: str) -> None:
    print(f"\n\033[1;36m▸ {msg}\033[0m")


def _point_stores_at_demo() -> None:
    """모든 저장소를 시연 뿌리로 돌린다. **운영 `data/` 를 열지 않는다.**

    ⚠️ 싱글턴의 `db_path` 를 갈아끼운다 — 시험이 쓰는 것과 같은 격리 방식이다.
      `core/paths.py` 는 뿌리를 `__file__` 기준으로 잡으므로 환경변수로는 못 바꾼다."""
    if (os.path.abspath(TARGET_ROOT) == os.path.abspath(OPERATIONAL)
            and os.path.abspath(TARGET_ROOT) == os.path.abspath(DEMO_ROOT)):
        raise SystemExit("시연 뿌리가 운영 data/ 와 같습니다 — 멈춥니다.")
    os.makedirs(TARGET_ROOT, exist_ok=True)

    import core.app_preview as ap
    from core.collaboration_store import collaboration_store
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.scenario_inputs import scenario_inputs

    dp.data_preparation_store.db_path = os.path.join(TARGET_ROOT, "data_preparation.db")
    dp.data_preparation_store._prepared_for = None
    decision_ledger.db_path = os.path.join(TARGET_ROOT, "decision_ledger.db")
    collaboration_store.db_path = os.path.join(TARGET_ROOT, "collaboration.db")
    scenario_inputs._repo.db_path = os.path.join(TARGET_ROOT, "enterprise_context.db")
    ap.db_path = lambda audience: os.path.join(TARGET_ROOT, "app_data_preview.db")
    #: ⚠️ 인증 저장소가 빠져 있었다 — **로그인 세션이 운영 `data/auth.db` 에 쌓였다.**
    #:   시연 로그인이 운영 세션표를 건드리면, 운영에서 누가 언제 들어왔는지가 오염된다.
    from core.auth import auth_store
    auth_store.db_path = os.path.join(TARGET_ROOT, "auth.db")

    #: ⚠️⚠️ [2026-08-24 실측] **게시된 앱 보관소도 빠져 있었다.** 키트 앱을 만들면
    #:   `library/<release_id>/release.json` 이 생기는데, `library_paths._LIBRARY_DIR`
    #:   는 프로세스 작업 디렉터리 기준 상대경로("library")라 **운영 보관소**에 쌓였다.
    #:   실제로 시연에서 만든 앱 릴리스 2건이 저장소 루트의 `library/` 에 남아 있었다.
    #: ★ 봉인이 `data/` 만 막고 있었다 — 「열지 않습니다」를 찍으면서 다른 문으로 샜다.
    from core import library_paths
    library_paths._LIBRARY_DIR = os.path.join(TARGET_ROOT, "library")

    #: ★ 사용여부(후보/운영)도 시연 뿌리에. 안 그러면 시연 앱의 승격이 운영 표에 남는다.
    from core.program_lifecycle import program_lifecycle
    program_lifecycle.db_path = os.path.join(TARGET_ROOT, "program_lifecycle.db")
    program_lifecycle._ready = ""


def _org():
    """조직도 — **상위→하위 상속**을 볼 수 있게 두 단으로 세운다."""
    import api.deps as deps
    import core.org_directory as orgmod
    import core.scope_policy as sp
    from core.org_directory import OrgDirectory

    org = OrgDirectory(db_path=os.path.join(TARGET_ROOT, "org.db"))
    #: ⚠️ 강제가 꺼져 있으면 `resolve_scope` 가 전원 무제한을 돌려준다 — 그 상태에서는
    #:   권한 경계가 하나도 안 보이고, 시연이 「전부 되는 것」처럼 끝난다.
    sp._read = lambda: {"org_enforce": True}
    orgmod.org_directory = org
    deps.org_directory = org
    return org


def seed() -> str:
    from core import calc_baseline as cb
    from core import demo_vertical_slice as dv
    from core.data_preparation import models as m
    from core.data_preparation import snapshot_service as svc
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger

    store = dp.data_preparation_store
    sl = _slice()
    tenant, scope = dv.scope_of(sl)

    #: ⚠️ 문맥의 테넌트는 `config.ECM_DEFAULT_TENANT_ID` 가 정한다. 정본 CSV 의 테넌트와
    #:   다르면 화면이 자기 인스턴스를 못 본다 — 시연 뿌리에서는 정본 쪽에 맞춘다.
    #:
    #: ★★★ [2026-08-24] **운영 뿌리에 심을 때는 반대로 맞춘다.** 거기서는 설치본이
    #:   이미 쓰는 테넌트가 정본이고, 자료를 그쪽으로 심어야 한다.
    #:   ⚠️ 설정을 파일로 덮게 만들었다가 **시험 100건이 깨졌다** — `config` 를 import
    #:     시점에 파일에서 읽으면 시험이 개발자의 `data/` 에 의존하게 되고, 그 파일이
    #:     있는 기계에서만 빨강이 된다. 설정을 자료에 맞추지 말고 **자료를 설정에 맞춘다.**
    #:   ★ 조회 필터는 `kit_instances.tenant_id` **열**을 본다(CSV 행 내용이 아니다).
    #:     그래서 열만 설치본 값으로 심으면 정본 파일은 그대로 두고도 보인다.
    import config as cfg
    if TENANT_OVERRIDE:
        tenant = TENANT_OVERRIDE
    else:
        cfg.ECM_DEFAULT_TENANT_ID = tenant

    _ensure_company_name(tenant)

    say("① 조직·사용자")
    if SKIP_ORG:
        #: 운영 파종 — **이미 있는 조직을 쓴다.** 강제 정책만 켠다(그것이 `_org()` 의
        #: 나머지 절반이고, 없으면 범위 경계가 화면에서 보이지 않는다).
        import core.scope_policy as sp
        from core.org_directory import org_directory as org
        sp._read = lambda: {"org_enforce": True}
        print(f"  ✓ 기존 조직을 씁니다 — 부서 {len(org.list_departments())}개")
    else:
        org = _org()
        for dept, name, parent, node in ((DEPT_HQ, "본사", "", "corp-afs"),
                                         (DEPT_PLANT, "제련공장", DEPT_HQ, scope)):
            try:
                org.create_department(dept, name, parent_id=parent, scope_node_id=node,
                                      actor="demo-seed")
            except Exception:
                org.update_department(dept, parent_id=parent, scope_node_id=node,
                                      actor="demo-seed")
        org.upsert_user(USER_ADMIN, "권희권", primary_dept_id=DEPT_HQ, is_admin=True,
                        is_data_admin=True, actor="demo-seed")
        org.set_user_roles(USER_ADMIN, {DEPT_HQ: "manager"}, actor="demo-seed")
        org.upsert_user(USER_RUNNER, "실행자 (예시)", primary_dept_id=DEPT_PLANT,
                        actor="demo-seed")
        org.set_user_roles(USER_RUNNER, {DEPT_PLANT: "member"}, actor="demo-seed")
        print(f"  ✓ {DEPT_HQ}(corp-afs) → {DEPT_PLANT}({scope}) · 사용자 2명")

    say("② 정본 키트와 인증판")
    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=tenant, scope_node_id=scope, entity_mode="REAL",
        label="첫 수직 시연 — 비철 제련")

    #: ★★★ [2026-08-24 실측] **소유권 결속을 인증보다 먼저 심는다. 순서가 통제다.**
    #:
    #: 색인(`scope_index.write_conn`)은 **인증 시점**의 소유권을 봉인한다. 그래서 인증
    #:   뒤에 결속을 만들면 색인이 그것을 모르고, 해석기가 정확히 거부한다:
    #:
    #:       「이 색인은 소유권 결속이 없던 때에 만들어졌는데 지금은 결속이 있습니다 —
    #:        재물질화가 필요합니다(색인이 모르는 승인을 권한으로 쓰지 않습니다)」
    #:
    #: ★ 그 거부는 **옳다.** 나중에 만든 승인을 소급 적용하면, 결속을 바꿔치기해 과거
    #:   판정을 뒤집을 수 있다. 우회(발효일을 인증 이전으로 주기)하지 않고 **순서를**
    #:   바로잡는다 — 실제 운영에서도 「소유를 정하고 나서 인증한다」가 맞는 차례다.
    #: ⚠️ 이 줄을 아래 인증 루프 뒤로 옮기지 말 것. 옮기면 색인이 소유자를 빈 값으로
    #:   봉인하고, 경로 계산이 **한 줄도** 성립하지 않는다(그 상태로 한동안 돌았다 —
    #:   스텁 해석기가 가려 주고 있었다).
    say("②-1 데이터셋 소유권 결속(인증보다 **먼저**)")
    _own = seed_ownership(tenant, scope, dv.kit_dataset_keys())
    print(f"  ✓ 소유권 결속 {_own}건")

    for key in dv.SLICE_KEYS:
        rows, cols = sl[key]
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id=tenant,
            scope_node_id=scope, entity_mode="REAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv",
                          workspace_root=os.path.join(TARGET_ROOT, "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})
    #: ★★★ [2026-08-23] **앱이 요구하는 나머지도 심는다.**
    #:
    #: ⚠️⚠️ 종전에는 7종만 심었다. 그래서 준비도 보드의 「지금 만들 수 있는 것」이
    #:   APP-01~05 **전부 막힘**이었고, 12분 여정의 「키트로 앱 생성」 칸이 한 번도
    #:   열리지 않았다 — 정본 CSV 35종이 **전부 있는데** 심지 않았을 뿐이다.
    #: ★ `SLICE_KEYS` 는 늘리지 않는다. 그쪽은 수직 폐루프 계산이 쓰는 최소 집합이고,
    #:   합치면 계산 경로의 뜻이 바뀐다(부분집합 시각 규칙도 그쪽에만 있다).
    #: ⚠️ 앱용은 **자르지 않고** 통째로 심는다 — 앱 화면에서 「왜 일부만 보이나」가
    #:   되면 그것은 다른 문제로 읽힌다.
    extra = [k for k in dv.kit_dataset_keys() if k not in set(dv.SLICE_KEYS)]
    for key in extra:
        rows, cols = dv.read_full(key)
        if not rows:
            #: ⚠️ 빈 자료를 인증하지 않는다 — 「인증됐는데 0행」은 화면에서
            #:   「자료가 없다」와 구분되지 않는다.
            print(f"    · {key} 건너뜀 — 정본에 행이 없다")
            continue
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id=tenant,
            scope_node_id=scope, entity_mode="REAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv",
                          workspace_root=os.path.join(TARGET_ROOT, "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})
    print(f"  ✓ {inst['instance_id']} · 인증판 {len(dv.SLICE_KEYS)}종(수직 경로) "
          f"+ {len(extra)}종(앱용)")

    say("③ 온톨로지 계약과 관계 3건")
    _seed_ontology(tenant, scope, decision_ledger)

    say("④ 계산 기준선 봉인")
    a = dv.assumptions(sl)
    cb.seal(store, instance_id=inst["instance_id"], tenant_id=tenant,
            entity_mode="REAL", scope_node_id=scope, actor=USER_ADMIN,
            rationale="첫 수직 시연 기준선",
            sales_allocation=a["sales_allocation"],
            recognition_span_days=a["recognition_span_days"],
            baseline_recognition=a["baseline_recognition"])
    print("  ✓ 배분·인식규칙·기준 인식일")

    print("\n⚠️ **계산 능력 실행 승인은 심지 않았다.** 「계산 실행 승인 · 시연 초기화」")
    print("   화면에서 사람이 눌러야 한다 — 심어 두면 그 화면이 도는지 확인할 수 없다.")
    return inst["instance_id"]


def _seed_ontology(tenant: str, scope: str, decision_ledger) -> None:
    from core import app_policy, ontology_resolve
    from core import ontology_runtime as ortm
    from core import path_calculation as pc
    from core.ontology_resolvers import product_approval_resolver
    from core.ontology_runtime import ObjectRef, OntologyRuntime, RelationProposal
    import api.routes.calculation_control as cal
    import api.routes.ontology_control as onto
    import core.org_directory as orgmod
    from core import demo_vertical_slice as dv
    from core.ontology_resolvers import product_object_scope_resolver

    #: ★ 사슬은 **정본 자료에서** 뽑는다(`chain_from_slice` 주석 참조).
    chain = chain_from_slice(_slice(scope))

    #: ★★★ [2026-08-24] **제품 해석기를 쓴다. 스텁을 심지 않는다.**
    #:
    #: ⚠️⚠️ 종전에는 «무엇을 묻든 찾았다» 고 답하는 스텁을 심었다:
    #:
    #:     def resolver(ref, rctx):
    #:         return ontology_resolve.found(ResourceScope(... BOUND))
    #:
    #:   그 위에서는 어떤 ID 를 넣어도 경로가 나온다 — 실제로 사슬은 색인에 없는 지어낸
    #:   ID(`SHP-001`)였는데도 화면에 「경로 3개」가 떴다. 제품 경로로는 한 줄도 성립하지
    #:   않는 상태였다. 스텁 위의 초록은 아무것도 증명하지 않는다.
    #: ★ 제품 해석기로 심으면 **파종 자체가 검증**이 된다 — 해석되지 않는 것을 심으려 하면
    #:   `propose_relation` 이 거기서 죽는다.
    rt = OntologyRuntime(os.path.join(TARGET_ROOT, "ontology.db"),
                         product_object_scope_resolver, product_approval_resolver)
    contract = {
        "contract_id": "G2-FIRST-VERTICAL-ONTOLOGY", "contract_version": "1.0.0",
        "status": "APPROVED",
        "relation_types": [{"id": "AFFECTS", "name_ko": "영향을 줌",
                            "inverse": "AFFECTED_BY", "quantitative": True}],
        "constraints": [{"subject": f"dataset:{s}", "relation": "AFFECTS",
                         "object": f"dataset:{o}", "evidence": ["승인된 지연 모형"],
                         "calculation_ref": ref}
                        for (s, _si, o, _oi), ref in zip(chain, pc.SEGMENTS)],
        #: 자리표시자로 지문을 얻고 **실제 원장 사건** id 로 바꿔 설치한다.
        #: ★★★ [2026-08-24 실측] 발효일을 **인증 시각 이후**로 잡는다.
        #:
        #: ⚠️ 종전 `2026-01-01` 은 자료의 **업무 시각**을 따른 값인데, 끝점 해석은
        #:   **인증 시각**(`certified_at`, 벽시계)을 본다. 두 축을 같은 값으로 물으면
        #:   「그 시점에는 아직 인증되지 않았습니다」로 관계 제안 자체가 죽는다.
        #: ★ 업무 시각(행 선택)과 시스템 시각(인증·발효)은 **다른 축**이다. 행은 이미
        #:   `build_slice(AS_OF)` 가 업무 시각으로 골랐고, 여기서 정하는 것은 «이 계약이
        #:   언제부터 유효한가» 다 — 그것은 심는 지금이다.
        "approval": {"approved_by": USER_ADMIN, "decision_ledger_id": "placeholder",
                     "effective_from": _now_iso()},
    }
    fp = rt.validate_model_contract(contract)["contract_fingerprint"]
    ev = decision_ledger.append(
        event_type="ONTOLOGY_MODEL_APPROVED", subject_type="ontology_model_contract",
        subject_id=fp, actor_type="user", actor_id=USER_ADMIN, decision="APPROVED",
        rationale="첫 수직 온톨로지 계약 승인", tenant_id=tenant, entity_mode="REAL")
    contract["approval"]["decision_ledger_id"] = ev["event_id"]
    rt.install_model_contract(contract, USER_ADMIN)

    subj = app_policy.Subject(
        user_id=USER_ADMIN, scope=orgmod.org_directory.resolve_scope(USER_ADMIN),
        ctx={"tenant_id": tenant, "entity_mode": "REAL", "scope_node_id": scope},
        session_id="demo-seed", blocked_reason="")
    for (s_t, s_i, o_t, o_i), ref in zip(chain, pc.SEGMENTS):
        made = rt.propose_relation(RelationProposal(
            subject=ObjectRef("dataset", s_t, s_i), relation_type_id="AFFECTS",
            object=ObjectRef("dataset", o_t, o_i), tenant_id=tenant,
            enterprise_scope_id=scope, entity_mode="REAL",
            #: ★ 관계의 발효일도 **시스템 시각**이다(위 계약 주석과 같은 이유).
            #:   끝점은 `certified_at` 으로 해석되므로 인증보다 앞선 발효일을 주면
            #:   「그 시점에는 아직 인증되지 않았습니다」로 제안 자체가 죽는다.
            owner_organization_id=DEPT_PLANT, effective_from=_now_iso(),
            origin="derived", evidence_refs=("SNAPSHOT:LOG-02:v1",),
            calculation_ref=ref), USER_PROPOSER, subj)
        rid = made["relation_id"]
        rt.submit(rid, USER_PROPOSER, subj)
        rev = decision_ledger.append(
            event_type="ONTOLOGY_RELATION_APPROVED", subject_type="ontology_relation",
            subject_id=rid, actor_type="user", actor_id=USER_ADMIN, decision="APPROVED",
            rationale="첫 수직 경로 관계 승인", tenant_id=tenant, entity_mode="REAL")
        rt.approve(rid, USER_ADMIN, rev["event_id"], subj)

    #: 제품 전역 런타임을 이 시연 런타임으로 돌린다.
    cal.ontology_runtime = rt
    ortm.ontology_runtime = rt
    onto.router.routes[:] = onto.create_router(rt).routes
    print(f"  ✓ 계약 1건 · 관계 {len(chain)}건(승인) — {_chain_text(chain)}")


def _ensure_company_name(tenant: str) -> None:
    """회사의 **사람이 읽는 이름**을 세운다. 멱등이다.

    ⚠️⚠️ [2026-08-25] 없으면 상단 문맥이 `tenant-afs-demo-materials` 라는 기계 식별자를
      사람에게 그대로 보여 준다(승인 시안의 그 자리는 「LS MnM」이다).
    ★ 이름은 저장소가 갖는다 — 클라이언트가 id 를 잘라 만들면 회사 이름이 코드가 되고,
      이름을 바꾸려면 배포를 해야 한다.
    ⚠️ 처음 심을 때만 부르면 **이미 심어진 뿌리는 영영 이름이 없다** — 데이터셋 보충과
      같은 함정이라, 두 경로에서 모두 부른다."""
    try:
        from core.enterprise_context.repository import ecm_repository
        ecm_repository.db_path = os.path.join(TARGET_ROOT, "enterprise_context.db")
        got = ecm_repository.get_tenant(tenant)
        if got and got.get("name_ko") == DEMO_COMPANY_NAME:
            print(f"  회사 이름 그대로 — «{DEMO_COMPANY_NAME}»")
            return
        ecm_repository.upsert_tenant(tenant, DEMO_COMPANY_NAME,
                                     legal_name=DEMO_COMPANY_LEGAL)
        print(f"  ✓ 회사 이름 «{DEMO_COMPANY_NAME}» ({tenant})")
    except Exception as e:
        #: ⚠️ 삼키지 않는다 — 이름이 없으면 화면이 식별자로 되돌아가고, 그 이유를 알아야 한다.
        print(f"  ⚠️ 회사 이름을 심지 못했습니다: {e}")


def _top_up(instance_id: str) -> None:
    """이 인스턴스에 **아직 없는 계약키만** 인증까지 올린다. 멱등이다.

    ⚠️ 이미 있는 것을 다시 심지 않는다 — 판이 둘이 되면 화면에서 어느 것이 최신인지
      사람이 판단해야 한다.
    ⚠️ 빈 자료는 인증하지 않는다 — 「인증됐는데 0행」은 「자료가 없다」와 구분되지 않는다."""
    from core import demo_vertical_slice as dv
    from core.data_preparation import models as m
    from core.data_preparation import snapshot_service as svc
    from core.data_preparation.store import data_preparation_store as store

    inst = store.get_instance(instance_id)
    if not inst:
        print("  ⚠️ 인스턴스를 읽지 못해 보충을 건너뜁니다.")
        return
    want = dv.kit_dataset_keys()
    missing = [k for k in want if not store.active_binding(instance_id, k)]
    if not missing:
        print(f"  보충할 것 없음 — 계약키 {len(want)}종이 모두 결속돼 있습니다.")
        return

    #: ★ 여기서도 **결속을 먼저** 심는다(`seed()` 의 같은 주석 참조). 보충 경로만
    #:   빠뜨리면 「7종은 되는데 나머지 28종은 안 되는」 절반짜리 상태가 된다.
    seed_ownership(str(inst["tenant_id"]), str(inst["scope_node_id"]), missing)

    made, skipped = 0, []
    for key in missing:
        rows, cols = dv.read_full(key)
        if not rows:
            skipped.append(key)
            continue
        b = store.create_binding(
            instance_id=instance_id, dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=str(inst["tenant_id"]), scope_node_id=str(inst["scope_node_id"]),
            entity_mode=str(inst["entity_mode"]))
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv",
                          workspace_root=os.path.join(TARGET_ROOT, "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})
        made += 1
    print(f"  ✓ 보충 {made}종 (없던 것 {len(missing)}종 중)")
    if skipped:
        #: ★ 건너뛴 것을 **말한다.** 조용히 빼면 「왜 그 앱이 아직 막혔나」에 답할 수 없다.
        print(f"  · 정본에 행이 없어 건너뜀 {len(skipped)}종: {skipped}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="시연 뿌리를 비우고 다시 심는다")
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    if args.reset:
        #: ⚠️⚠️ [2026-08-23 실측] `ignore_errors=True` 는 **조용히 실패한다.** 파일이
        #:   잠겨 있으면(시연 서버가 떠 있으면) 아무것도 안 지우고 넘어가는데, 그
        #:   다음 줄은 「비웠습니다」라고 찍었다. 그리고 「이미 심어져 있습니다」로
        #:   빠져 **다시 심지 않았다** — 사용자는 새로 심었다고 믿는다.
        #: ★ 지웠는지 **확인**한다. 못 지웠으면 멈추고 이유를 말한다.
        shutil.rmtree(DEMO_ROOT, ignore_errors=True)
        left = sorted(os.listdir(DEMO_ROOT)) if os.path.isdir(DEMO_ROOT) else []
        if left:
            print(f"✗ 시연 뿌리를 비우지 못했습니다: {DEMO_ROOT}")
            print(f"  남은 것 {len(left)}개 — 예: {left[:4]}")
            print("  시연 서버가 떠 있으면 내린 뒤 다시 실행하십시오.")
            return 2
        print(f"시연 뿌리를 비웠습니다: {DEMO_ROOT}")

    #: ★ 봉인이 **먼저**다. `_point_stores_at_demo()` 가 core 모듈을 import 하는 순간
    #:   그 모듈들이 자기 기본 경로를 정하므로, 그 전에 뿌리가 바뀌어 있어야 한다.
    _seal_operational_data()
    _point_stores_at_demo()
    print(f"시연 데이터 뿌리: {DEMO_ROOT}")
    print(f"운영 data/ 는 열지 않습니다: {OPERATIONAL}")

    #: ⚠️ `list_instances` 는 **보이는 범위만** 돌려준다 — 범위를 안 주면 빈 목록이다.
    #:   그 빈 목록을 「아직 안 심었다」로 읽고 다시 심었더니 관계가 중복돼 기간
    #:   겹침으로 죽었다. 여기서는 「심었는가」만 물으므로 저장소를 직접 센다.
    from core.data_preparation import store as dp

    with dp.data_preparation_store.transaction() as conn:
        existing = [dict(r) for r in conn.execute(
            "SELECT instance_id, scope_node_id FROM kit_instances "
            "WHERE status='active' ORDER BY created_at")]
    if existing:
        #: ⚠️ 이미 있으면 **다시 심지 않는다.** 두 번 심으면 인스턴스가 둘이 되고,
        #:   화면에서 어느 것이 진짜인지 알 수 없다.
        _org()
        print(f"\n이미 심어져 있습니다(인스턴스 {len(existing)}개). 다시 심으려면 --reset")
        inst = existing[0]["instance_id"]
        #: 온톨로지 런타임만 시연 파일로 돌린다.
        _rewire_ontology_only()
        #: ★★★ [2026-08-23] **부족한 것만 채운다.**
        #:
        #: ⚠️⚠️ 종전에는 여기서 아무것도 안 했다. 그래서 앱용 28종이 추가된 뒤에도
        #:   기존 시연 뿌리는 **영원히 7종인 채**였고, 채우려면 `--reset` 으로 온톨로지·
        #:   기준선까지 다 날려야 했다 — 「보충」과 「초기화」는 다른 일이다.
        #: ★ 더하기만 한다. 이미 있는 결속·판은 건드리지 않는다.
        _top_up(inst)
        #: ★ 이름도 같은 규칙 — 이미 심어진 뿌리에도 채운다.
        from core import demo_vertical_slice as _dv
        _ensure_company_name(_dv.scope_of(_slice())[0])
    else:
        inst = seed()

    if args.seed_only:
        print(f"\n인스턴스: {inst}")
        return 0

    say("기동")
    print(f"  화면: http://127.0.0.1:5173  (프런트는 따로 띄우십시오)")
    print(f"  서버: http://127.0.0.1:{args.port}")
    print(f"  로그인: {USER_ADMIN} · 초기 비밀번호는 `core/auth.py` 의 공통값")
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=args.port, reload=False)
    return 0


def _rewire_ontology_only() -> None:
    """이미 심어진 경우 — 온톨로지 런타임만 시연 파일로 돌린다."""
    from core import app_policy, ontology_resolve
    from core import ontology_runtime as ortm
    from core.ontology_resolvers import product_approval_resolver
    from core.ontology_runtime import OntologyRuntime
    import api.routes.calculation_control as cal
    import api.routes.ontology_control as onto
    from core import demo_vertical_slice as dv

    sl = _slice()
    tenant, scope = dv.scope_of(sl)
    import config as cfg
    cfg.ECM_DEFAULT_TENANT_ID = tenant

    def resolver(ref, rctx):
        return ontology_resolve.found(app_policy.ResourceScope(
            tenant_id=tenant, entity_mode="REAL", scope_node_id=scope,
            owner_dept_id=DEPT_PLANT, binding_state=app_policy.BOUND))

    rt = OntologyRuntime(os.path.join(TARGET_ROOT, "ontology.db"), resolver,
                         product_approval_resolver)
    cal.ontology_runtime = rt
    ortm.ontology_runtime = rt
    onto.router.routes[:] = onto.create_router(rt).routes


if __name__ == "__main__":
    raise SystemExit(main())
