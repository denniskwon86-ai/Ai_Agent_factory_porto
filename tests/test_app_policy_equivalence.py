"""★★★ [G1-B P0] **기존 `assert_release_*` 와 신규 PDP 의 동등성 대조.**

교차검토 `[G1-B-P0-REVIEW-75]` 의 지시:

> 기존 `assert_release_*` 를 곧바로 제거하지 않는다. 신규 PDP 가 **기존보다 동등하거나 더
> 엄격하다**는 것이 입증될 때까지 이중 판정해야 한다.

이 파일이 그 입증이다. 같은 사실을 두 판정기에 태우고 **안전 속성 하나**를 단언한다.

    PDP 가 허용하면 → 기존도 허용했어야 한다        (PDP ⊆ 기존)

이 방향이 중요하다. 반대(기존이 허용하면 PDP 도 허용)는 **성립하지 않아야 정상**이다 —
PDP 는 미바인딩·문맥 불일치·폐지 계정 같은 축을 새로 막기 때문이다. 그 «더 엄격해진 칸» 은
아래 `STRICTER_ON` 에 **미리 적어 두고**, 예상 밖의 칸이 생기면 실패시킨다.

⚠️ 「더 엄격하니 안전하다」로 끝내지 않는다. 엄격해진 칸이 **의도한 것인지** 칸마다 적는다 —
  의도하지 않은 엄격함은 기능을 끄는 것이고, 이 저장소는 그것으로 이미 여러 번 다쳤다.
"""
import pytest
from fastapi import HTTPException

import core.app_policy as ap


class _Scope:
    def __init__(self, read=(), write=(), unrestricted=False, can_manage_standard=False):
        self.readable_dept_ids = frozenset(read)
        self.writable_dept_ids = frozenset(write)
        self.unrestricted = unrestricted
        self.can_manage_standard = can_manage_standard

    def can_write(self, dept):
        return dept in self.writable_dept_ids

    def can_read(self, dept):
        return dept in self.readable_dept_ids


#: 대조 시나리오. `own` 은 **두 판정기에 똑같이 먹인다** — 한쪽에만 다른 사실을 주면
#: 그 대조는 아무것도 증명하지 못한다.
#:
#: `expect_stricter` : 이 칸에서 PDP 가 기존보다 엄격할 것으로 **예상**하는가.
#: `why`             : 엄격해진 이유(의도 확인용). 예상하지 않은 칸이면 빈 문자열.
SCENARIOS = [
    # ── 동등해야 하는 칸 ────────────────────────────────────────────────
    dict(name="자기 부서 자료 · 읽기", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         action=ap.READ, expect_stricter=False, why=""),
    dict(name="자기 부서 자료 · 쓰기", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         action=ap.WRITE, expect_stricter=False, why=""),
    #: ⚠️ 부서를 준다. 부서가 아예 없으면 `visibility_block_reason` 이 **주체 자체**를 막아
    #:   소유권 판정에 도달하지 못하고, 그러면 이 칸은 소유자 규칙을 시험하지 못한다.
    dict(name="소유자 본인 · 쓰기(타 부서 자원)", uid="me@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "sales", "owner_user_id": "me@x", "visibility": "dept"},
         action=ap.WRITE, expect_stricter=False, why=""),
    dict(name="무제한 권한자 · 쓰기", uid="boss@x",
         scope=_Scope(unrestricted=True),
         own={"dept_id": "sales", "owner_user_id": "", "visibility": "dept"},
         action=ap.WRITE, expect_stricter=False, why=""),
    dict(name="남의 부서 자료 · 읽기(둘 다 거부)", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "sales", "owner_user_id": "", "visibility": "dept"},
         action=ap.READ, expect_stricter=False, why=""),
    dict(name="읽기 권한만 · 쓰기(둘 다 거부)", uid="u@x",
         scope=_Scope(read={"hq"}, write=set()),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         action=ap.WRITE, expect_stricter=False, why=""),

    # ── PDP 가 더 엄격해지는 칸 (전부 의도된 강화) ──────────────────────
    dict(name="익명 · 읽기", uid="",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         action=ap.READ, expect_stricter=True,
         why="기존 읽기 판정에는 식별 요구가 없었다 — 누가 읽었는지 모르면 추적이 불가능하다"),
    dict(name="소유권 미기록 자원 · 읽기", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}), own=None,
         action=ap.READ, expect_stricter=True,
         why="기존은 «미기록은 막지 않는다» 였다. D-014 상 미지정은 전사 공용이 아니라 비노출"),
    dict(name="소유권 미기록 자원 · 쓰기", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}), own=None,
         action=ap.WRITE, expect_stricter=True,
         why="같은 이유. 신규 Host Runtime 자원에 읽기용 관대함을 쓰지 않는다"),
    dict(name="전사 공개(company) · 다른 부서", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "sales", "owner_user_id": "", "visibility": "company"},
         action=ap.READ, expect_stricter=True,
         why="기존은 company 를 테넌트 무관 전역 공개로 봤다. 문맥 안에서만 공개여야 한다"),
    dict(name="폐지된 계정 · 읽기", uid="dead@x",
         scope=_Scope(read={"hq"}, write={"hq"}), account_retired=True,
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         action=ap.READ, expect_stricter=True,
         why="기존 **읽기** 판정은 계정 상태를 보지 않았다 — 쓰기만 봤다"),
    dict(name="사용 중단된 자원 · 읽기", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         res_status="retired", action=ap.READ, expect_stricter=True,
         why="기존은 자원 상태를 보지 않았다 — 폐기된 데이터셋을 계속 읽을 수 있었다"),
    dict(name="다른 회사 문맥", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         ctx_tenant="tenant_other", action=ap.READ, expect_stricter=True,
         why="기존 릴리스 판정에는 문맥 축이 아예 없었다"),
    dict(name="다른 실행 모드(VIRTUAL 자원을 REAL 문맥에서)", uid="u@x",
         scope=_Scope(read={"hq"}, write={"hq"}),
         own={"dept_id": "hq", "owner_user_id": "", "visibility": "dept"},
         res_mode="VIRTUAL", action=ap.READ, expect_stricter=True,
         why="시험·가상 자료가 실제 문맥 화면에 섞이면 실제 진행처럼 보인다"),
]


def _setup(monkeypatch, sc):
    """두 판정기에 **같은 사실**을 먹인다. 반환: `(Principal, blocked_reason)`.

    ★★★ 여기가 이 파일의 핵심이다. 초판 하니스는 기존 판정에만 조직 저장소를 물리고 PDP 에는
      `blocked_reason=""` 을 줬다 — 그러자 「소유자 본인·쓰기」에서 **기존 거부 / PDP 허용**
      이라는 완화가 나왔다. 원인은 제품이 아니라 **대조가 불공정**했던 것이고, 그 사실이
      곧 어댑터 계약을 증명한다:

          라우트 어댑터는 `visibility_block_reason(p)` 를 **반드시** `Subject.blocked_reason`
          으로 넘겨야 한다. 넘기지 않으면 운영에서 똑같이 느슨해진다.

    ⚠️ 그래서 여기서도 그 값을 **실제 함수로 계산해** 넘긴다. 손으로 적으면 그 순간
      두 세계가 갈라지고, 갈라진 대조는 아무것도 증명하지 못한다."""
    import config
    import api.deps as deps
    from core.org_directory import org_directory

    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(deps, "_enforced", lambda: True, raising=False)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: (dict(sc["own"]) if sc.get("own") else None))
    #: 계정 상태는 기존 판정이 `get_user` 로 본다 — 같은 사실을 먹인다.
    active = not sc.get("account_retired")
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: ({"user_id": uid, "status": "active" if active else "retired"}
                                     if uid else None))
    p = deps.Principal(user_id=sc["uid"], scope=sc["scope"])
    return p, deps.visibility_block_reason(p)


def _run_old(sc, p):
    """기존 `assert_release_readable/writable` 를 태운다. 통과하면 True."""
    import api.deps as deps
    try:
        if sc["action"] in (ap.WRITE, ap.DELETE, ap.MANAGE):
            deps.assert_release_writable(p, "rel_1")
        else:
            deps.assert_release_readable(p, "rel_1")
        return True
    except HTTPException:
        return False


def _run_new(sc, blocked):
    """신규 PDP 를 **같은 사실**로 태운다. `(허용, 사유)`."""
    own = sc.get("own")
    res = ap.ResourceScope(
        tenant_id="tenant_default",
        entity_mode=sc.get("res_mode", "REAL"),
        #: 소유권 미기록 = 범위도 없다. 두 판정기에 같은 «없음» 을 먹이기 위한 값이다.
        scope_node_id="node_hq" if own else "",
        owner_user_id=(own or {}).get("owner_user_id", ""),
        owner_dept_id=(own or {}).get("dept_id", ""),
        binding_state=ap.BOUND,
        status=sc.get("res_status", "active"))
    subject = ap.Subject(
        user_id=sc["uid"], scope=sc["scope"], session_id="sess_1",
        #: ★ 어댑터가 넘길 값을 **그대로** 넘긴다(위 `_setup` 주석).
        blocked_reason=blocked,
        ctx={"tenant_id": sc.get("ctx_tenant", "tenant_default"),
             "entity_mode": "REAL", "scope_node_id": ""},
        via="session")
    d = ap.decide(subject, res, sc["action"])
    return d.allowed, d.reason


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_PDP_는_기존보다_느슨해지지_않는다(monkeypatch, sc):
    """★★★ **안전 속성**: PDP 가 허용하면 기존도 허용했어야 한다.

    이 단언이 깨지면 «PDP 로 바꾸는 것만으로 권한이 넓어진» 상태이고, 교차검토가
    금지한 바로 그것이다."""
    p, blocked = _setup(monkeypatch, sc)
    old = _run_old(sc, p)
    new, reason = _run_new(sc, blocked)
    assert not (new and not old), (
        f"PDP 가 기존보다 느슨하다 — 기존 거부 / PDP 허용: {sc['name']}")


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_엄격해진_칸이_예상과_일치한다(monkeypatch, sc):
    """⚠️ 「더 엄격하니 안전하다」로 끝내지 않는다.

    예상하지 않은 칸이 엄격해지면 그것은 **기능을 끄는 변경**이다 — 이 저장소는
    「통제를 조이다가 기능을 끈」 사고를 이미 겪었다. 그래서 칸마다 미리 적어 두고 대조한다."""
    p, blocked = _setup(monkeypatch, sc)
    old = _run_old(sc, p)
    new, reason = _run_new(sc, blocked)
    stricter = old and not new
    assert stricter == sc["expect_stricter"], (
        f"{sc['name']}: 기존={'허용' if old else '거부'} · PDP={'허용' if new else '거부'}"
        f"({reason}) — 예상 엄격={sc['expect_stricter']}")
    if stricter:
        assert sc["why"], "엄격해진 이유가 적혀 있지 않다"


def test_대조가_한쪽으로_굳지_않았다(monkeypatch):
    """★ **대조군.** 시나리오가 전부 「둘 다 거부」거나 전부 「둘 다 허용」이면 이 파일은
    아무것도 증명하지 못한다. 세 종류가 모두 존재하는지 본다."""
    kinds = set()
    for sc in SCENARIOS:
        p, blocked = _setup(monkeypatch, sc)
        kinds.add((_run_old(sc, p), _run_new(sc, blocked)[0]))
    assert (True, True) in kinds, "둘 다 허용하는 칸이 없다 — 통제가 전부 막는 쪽으로 굳었다"
    assert (True, False) in kinds, "엄격해진 칸이 없다 — 보정이 실제로 적용됐는지 알 수 없다"
    assert (False, False) in kinds, "둘 다 거부하는 칸이 없다"


def test_동등성_표를_출력한다(monkeypatch, capsys):
    """★ 사람이 읽을 표. 실패하지 않는다 — 보고서에 그대로 붙일 근거를 만든다.

    ⚠️ 이 표는 «지금» 의 사실이다. 판정이 바뀌면 표도 바뀐다 — 문서에 박제하지 말고
      이 시험을 다시 돌려서 얻는다."""
    rows = []
    for sc in SCENARIOS:
        p, blocked = _setup(monkeypatch, sc)
        old = _run_old(sc, p)
        new, reason = _run_new(sc, blocked)
        verdict = ("동등" if old == new else
                   ("★강화" if old and not new else "⚠️완화"))
        rows.append((sc["name"], sc["action"], "허용" if old else "거부",
                     "허용" if new else f"거부({reason})", verdict))
    width = max(len(r[0]) for r in rows)
    lines = ["", f"{'시나리오'.ljust(width)} | {'행동':6s} | {'기존':4s} | {'PDP':28s} | 판정",
             "-" * (width + 55)]
    for n, a, o, w, v in rows:
        lines.append(f"{n.ljust(width)} | {a:6s} | {o:4s} | {w:28s} | {v}")
    print("\n".join(lines))
    #: 완화가 하나라도 있으면 표만 찍고 넘어가지 않는다.
    assert not any(r[4] == "⚠️완화" for r in rows)
