"""★★★ [G1-B05] **지속형 관측과 전환 게이트** — 「전환해도 되는가」를 표본으로 판정한다.

교차검토 B05 지적:

> 현재 `policy_shadow` 는 프로세스 메모리만 사용합니다. 재시작하면 관측값이 사라집니다.
> 더 큰 문제는 `safe_to_switch` 가 `looser==0 and error==0 and total>0` 뿐이라는 점입니다.
> **읽기 요청 한 건만 일치해도 `True` 가 될 수 있습니다.**

## 이 파일이 지키는 다섯 가지

1. 관측이 **재시작 뒤에도 남는다**(게이트 근거는 영구 기록이다).
2. 게이트는 **여섯 작업 × 허용·거부** 표본을 요구한다.
3. 게이트는 **부정 시나리오 표본**을 요구하고, 그 라벨은 **PDP 사유에서 읽는다**
   (호출자가 붙이면 하니스가 자기 자신과 합의한 값이 된다).
4. **설명되지 않은 강화**도 막는다 — 권한 확대만 사고인 것이 아니다.
5. **업무 데이터와 토큰 전문이 텔레메트리에 남지 않는다.**
"""
import pytest

from core import app_policy as ap
from core.policy_shadow import (EXPLAINED_STRICTER, MIN_TOTAL, REQUIRED_OPS,
                                REQUIRED_SCENARIOS, UNKNOWN_REASON, _ShadowObserver)


@pytest.fixture()
def obs(tmp_path):
    """★ 격리된 파일. 운영 `data/policy_shadow.db` 를 절대 건드리지 않는다 —
    이 표는 접근 통제를 통째로 갈아 끼우는 근거다."""
    return _ShadowObserver(db_path=str(tmp_path / "shadow.db"))


def _fill(o, *, ops=REQUIRED_OPS, scenarios=True, n=6):
    """게이트를 열 수 있는 **최소한의 온전한 표본**을 만든다."""
    for op in ops:
        for _ in range(n):
            o.observe(path="p", action="read", old_allowed=True, new_allowed=True, op=op)
        #: ⚠️ 여기서 `DENY_SCOPE` 를 쓰면 «다른 조직 범위» 시나리오가 **공짜로 덮인다** —
        #:   그러면 그 칸이 빠진 것을 잡는 시험이 거짓 초록이 된다(실제로 그렇게 걸렸다).
        #:   어느 시나리오와도 이어지지 않은 사유를 쓴다.
        o.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                  new_reason=ap.DENY_RETIRED, op=op)
    if scenarios:
        for reasons in REQUIRED_SCENARIOS.values():
            o.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                      new_reason=reasons[0], op="data.list")


# ── ① 재시작 뒤에도 남는다 ────────────────────────────────────────────────

def test_관측이_프로세스를_넘어_남는다(tmp_path):
    """★★★ 재시작하면 사라지는 근거로 전환을 결정하면, 배포 직후 **표본 0 인 상태**가
    「어긋남 0」으로 읽힌다."""
    path = str(tmp_path / "shadow.db")
    a = _ShadowObserver(db_path=path)
    a.observe(path="GET /records", action="read", old_allowed=True, new_allowed=True,
              op="data.list")
    b = _ShadowObserver(db_path=path)             # 새 프로세스처럼
    assert b.switch_gate()["counts"]["total"] == 1, "재시작 뒤 관측이 사라졌다"


def test_기록이_실패해도_요청은_살고_게이트는_닫힌다(obs, monkeypatch):
    """⚠️ 방향이 중요하다 — 「기록이 안 되니 그냥 전환」이 아니라 **표본이 없으니 닫힘**이다."""
    monkeypatch.setattr(obs, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("디스크")))
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=True, op="data.list")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any("저장되지 않" in b for b in g["blockers"]), g["blockers"]


# ── ② 한 건으로는 열리지 않는다 ───────────────────────────────────────────

def test_읽기_한_건으로는_전환_게이트가_열리지_않는다(obs):
    """★★★ 교차검토가 지적한 바로 그 칸이다."""
    obs.observe(path="GET /records", action="read", old_allowed=True, new_allowed=True,
                op="data.list")
    g = obs.switch_gate()
    assert (g["counts"]["looser"], g["counts"]["error"]) == (0, 0)
    assert g["safe_to_switch"] is False, "어긋남 0 만으로 열렸다"


def test_칸이_다_덮였어도_표본이_너무_적으면_막는다(obs):
    """★★ 각 칸을 «한 번씩» 눌러 본 것과 «관측했다» 는 다르다.

    ⚠️ 이 시험이 없으면 `MIN_TOTAL` 을 1로 낮춰도 아무도 모른다(변이 검사에서 생존했다).
      최소 표본은 덮임 하한(6작업×2 + 시나리오 6 = 18)보다 **위에** 있어야 뜻이 있다."""
    _fill(obs, n=1)
    g = obs.switch_gate()
    assert all(s["allow"] and s["deny"] for s in g["op_coverage"].values()), "칸이 안 덮였다"
    assert all(g["scenario_coverage"].values()), "시나리오가 안 덮였다"
    assert g["counts"]["total"] < MIN_TOTAL
    assert g["safe_to_switch"] is False
    assert any("표본" in b for b in g["blockers"]), g["blockers"]


def test_온전한_표본이면_열린다(obs):
    """★ 대조군. 이것이 없으면 «무조건 닫힘» 인 게이트도 위 시험을 전부 통과한다."""
    _fill(obs)
    g = obs.switch_gate()
    assert g["safe_to_switch"] is True, g["blockers"]
    assert g["counts"]["total"] >= MIN_TOTAL


# ── ③ 작업별 · 허용거부 양쪽 표본 ─────────────────────────────────────────

@pytest.mark.parametrize("missing", list(REQUIRED_OPS))
def test_한_작업이라도_표본이_없으면_막는다(obs, missing):
    """⚠️ 읽기만 눌러 보고 전환하면 쓰기 통제는 **한 번도 대조되지 않은 채** 넘어간다."""
    _fill(obs, ops=tuple(o for o in REQUIRED_OPS if o != missing))
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any(missing in b for b in g["blockers"]), g["blockers"]


def test_허용만_있고_거부가_없으면_막는다(obs):
    """★★ 「전부 허용」하는 판정기도 허용 표본만으로는 통과한다 — 거부 쪽이 대조군이다."""
    for op in REQUIRED_OPS:
        for _ in range(MIN_TOTAL):
            obs.observe(path="p", action="read", old_allowed=True, new_allowed=True, op=op)
    for reasons in REQUIRED_SCENARIOS.values():
        obs.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                    new_reason=reasons[0], op="data.list")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any("허용·거부" in b for b in g["blockers"]), g["blockers"]


def test_작업_표본은_PDP_의_답으로_센다(obs):
    """★ 전환 후에 실제로 쓰일 판정은 PDP 쪽이다. 기존 판정으로 세면 **전환 후의 모습**을
    세지 않는 것이 된다."""
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=False,
                new_reason=ap.DENY_SCOPE, op="data.get")
    assert obs.switch_gate()["op_coverage"]["data.get"] == {"allow": 0, "deny": 1}


def test_앱이_부를_수_없는_라우트는_작업_표본이_아니다(obs):
    """⚠️ 「관리 화면에서 눌러 봤으니 덮였다」가 되면 게이트가 무의미해진다."""
    for _ in range(MIN_TOTAL * 2):
        obs.observe(path="POST /datasets", action="manage", old_allowed=True,
                    new_allowed=True, op="")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert all(v == {"allow": 0, "deny": 0} for v in g["op_coverage"].values())


# ── ④ 부정 시나리오 — 라벨을 지어낼 수 없다 ───────────────────────────────

@pytest.mark.parametrize("scenario", list(REQUIRED_SCENARIOS))
def test_부정_시나리오가_빠지면_막는다(obs, scenario):
    """★★★ 만료·재사용·다른 사용자·다른 앱·다른 조직·문맥 불일치 —
    이 칸들은 눌러 보지 않으면 표본이 아예 생기지 않는다. **없는 것은 «안전» 이 아니라 «모름»**."""
    _fill(obs, scenarios=False)
    for name, reasons in REQUIRED_SCENARIOS.items():
        if name == scenario:
            continue
        obs.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                    new_reason=reasons[0], op="data.list")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any(scenario in b for b in g["blockers"]), g["blockers"]


def test_시나리오_라벨은_PDP_사유에서만_나온다(obs):
    """★★ 호출자가 「이번은 다른-앱 시나리오다」라고 선언하게 두면 그 라벨은 하니스가
    **자기 자신과 합의한 값**이 된다. 라벨을 만들려면 실제로 그 판정을 통과시켜야 한다.

    ⚠️ 그리고 모르는 문자열은 사유로 저장되지 않는다 — `UNKNOWN` 이 된다."""
    obs.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                new_reason="다른 앱의 데이터", op="data.list")     # 시나리오 «이름» 을 넣어 본다
    g = obs.switch_gate()
    assert g["scenario_coverage"]["다른 앱의 데이터"] == 0, "이름만으로 시나리오가 덮였다"
    assert g["reasons_seen"] == [UNKNOWN_REASON]


def test_모든_필수_시나리오가_실제_거부_사유와_이어져_있다():
    """⚠️ 사유 상수가 이름이 바뀌면 시나리오는 **영원히 0** 이 되고, 게이트는 영원히 닫힌다
    (닫히는 쪽이라 사고는 아니지만, 이유를 아무도 못 찾는다)."""
    known = {v for k, v in vars(ap).items() if k.startswith("DENY_")}
    for name, reasons in REQUIRED_SCENARIOS.items():
        assert reasons, name
        for r in reasons:
            assert r in known, f"{name} 이 존재하지 않는 사유를 가리킨다: {r}"


# ── ⑤ 설명되지 않은 강화 ──────────────────────────────────────────────────

def test_설명되지_않은_강화는_막는다(obs):
    """★★★ 권한 확대만 사고가 아니다. 예상하지 않은 사유로 강화되면 **전환하는 순간
    지금 되던 일이 안 되게 된다** — 그리고 그 원인을 아무도 모른다."""
    _fill(obs)
    #: ⚠️ 예시로 **아직 없는 사유**를 쓴다. 실재하는 코드를 쓰면 그것이 예상 목록에 추가되는
    #:   날 이 시험이 조용히 무의미해진다(실제로 `TOKEN_CAPABILITY` 로 그렇게 됐다 —
    #:   앱 증명 축이 예정된 강화가 되면서 이 칸이 «설명됨» 으로 바뀌었다).
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=False,
                new_reason="AAA_없는_사유", op="data.list")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert g["unexplained_stricter"], "설명되지 않은 강화를 하나도 세지 않았다"


def test_예상된_강화는_막지_않는다(obs):
    """★ 대조군 — 전부 막으면 위 시험은 「아무 강화나 거부」로도 통과한다.

    ⚠️ `stricter` 가 0 이면 오히려 의심해야 한다. PDP 가 아무것도 강화하지 않는다는 뜻이고,
      그러면 이 관측은 「전환해도 안전하다」를 증명하지 못한다."""
    _fill(obs)
    for r in (ap.DENY_UNBOUND, ap.DENY_CONTEXT, ap.DENY_PRINCIPAL_BLOCKED):
        obs.observe(path="p", action="read", old_allowed=True, new_allowed=False,
                    new_reason=r, op="data.list")
    g = obs.switch_gate()
    assert g["counts"]["stricter"] == 3
    assert g["safe_to_switch"] is True, g["blockers"]


def test_모르는_사유는_설명된_강화로_치지_않는다(obs):
    """★★★ 새 거부 코드가 `KNOWN_REASONS` 등록 없이 생기면 `UNKNOWN` 으로 저장된다.
    그것까지 «설명됨» 으로 두면 이 검사가 **잡을 것이 하나도 남지 않는다.**

    ⚠️ 릴리스 판독 실패(`binding_state=INVALID`)는 `UNKNOWN` 이 아니라 `DENY_UNBOUND` 로
      나온다 — 판정기에서 확인했다. 그래서 `UNKNOWN` 을 넣을 이유가 없다."""
    assert UNKNOWN_REASON not in EXPLAINED_STRICTER
    _fill(obs)
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=False,
                new_reason="DENY_새로_생긴_코드", op="data.list")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert UNKNOWN_REASON in g["unexplained_stricter"]


def test_앱_증명_축의_강화는_예정된_것이다(obs):
    """★★ 런타임 경로에서 기존 판정은 사람만 보고 PDP 는 증명까지 본다. 만료·다른 세션·
    다른 앱은 전부 강화로 나오는데, 그것이 이 전환의 **목적**이다 — 「설명되지 않은 강화」로
    세면 게이트가 영원히 닫힌다."""
    _fill(obs)
    for r in (ap.DENY_TOKEN_EXPIRED, ap.DENY_TOKEN_SESSION_MISMATCH,
              ap.DENY_TOKEN_APP_MISMATCH, ap.DENY_MANIFEST_CAPABILITY):
        obs.observe(path="p", action="read", old_allowed=True, new_allowed=False,
                    new_reason=r, op="data.list")
    g = obs.switch_gate()
    assert g["unexplained_stricter"] == []
    assert g["safe_to_switch"] is True, g["blockers"]


# ── ⑥ 느슨함·관측 실패는 그대로 막는다 ───────────────────────────────────

def test_느슨한_칸이_하나라도_있으면_막는다(obs):
    _fill(obs)
    obs.observe(path="p", action="write", old_allowed=False, new_allowed=True, op="data.create")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any("느슨" in b for b in g["blockers"]), g["blockers"]


def test_관측_실패가_있으면_막는다(obs):
    """⚠️ 그 요청들에서 두 판정이 같았는지 **아무도 모른다.**"""
    _fill(obs)
    obs.error("read RuntimeError")
    g = obs.switch_gate()
    assert g["safe_to_switch"] is False
    assert any("실패" in b for b in g["blockers"]), g["blockers"]


def test_막을_때는_반드시_이유를_말한다(obs):
    """★ 「안 된다」만 있고 이유가 없으면 사람은 게이트를 끄는 쪽을 택한다."""
    assert obs.switch_gate()["blockers"], "표본 0 인데 이유가 없다"
    for b in obs.switch_gate()["blockers"]:
        assert len(b) > 10 and not b.endswith(":"), b


# ── ⑦ 업무 데이터·토큰은 남지 않는다 ──────────────────────────────────────

def test_모르는_사유는_저장되지_않고_UNKNOWN_이_된다(obs):
    """★★★ 사유 자리는 자유 문자열이 들어오기 가장 쉬운 곳이다 — 예외 메시지가 그대로
    흘러들면 거기에 **업무 데이터가 섞인다**(`ValueError(f"…{payload}…")`)."""
    obs.observe(path="p", action="read", old_allowed=False, new_allowed=False,
                new_reason="레코드 {'환자명': '홍길동'} 검증 실패", op="data.list")
    rows = obs._rows()
    assert rows[0]["reason"] == UNKNOWN_REASON
    assert "홍길동" not in str(rows[0])


def test_토큰_전문은_어느_자리에도_남지_않는다(obs):
    """★★★ 자리를 하나만 막으면 다음 사고는 다른 자리에서 난다. 전수로 본다.

    이 저장소의 비밀은 전부 **끊기지 않는 긴 문자열**이다 — 앱 증명 `app_<urlsafe24>`,
    세션 토큰 `token_urlsafe(32)`. 반면 여기 정상적으로 실리는 식별자는 짧거나 구분자가
    있다(`rel_ok` · `ds_<hex12>` · 이메일). 그 차이로 가린다."""
    from core.app_capability_token import PREFIX
    tok = PREFIX + "aB3dEf7gHi9jKlM1nOpQrS5t"
    obs.observe(path=f"GET /records?t={tok}", action="read", old_allowed=True,
                new_allowed=False, new_reason=tok, actor=tok, resource_id=tok, op=tok)
    row = obs._rows()[0]
    assert tok not in str(row), f"토큰 전문이 남았다: {row}"
    assert row["op"] == "", "작업 자리가 자유 문자열이다 — 표본을 지어낼 수 있다"


def test_정상_식별자는_가려지지_않는다(obs):
    """★ 대조군. 전부 가리면 위 시험은 「무조건 마스킹」으로도 통과하고, 그러면 관측이
    쓸모없어진다 — 「누가 어느 릴리스에서 막혔는가」에 답하지 못한다."""
    obs.observe(path="GET /records", action="read", old_allowed=True, new_allowed=True,
                actor="hikwon@lsmnm.com", resource_id="rel_ok", op="data.list")
    row = obs._rows()[0]
    assert (row["actor"], row["resource_id"]) == ("hikwon@lsmnm.com", "rel_ok")
    assert row["op"] == "data.list"


def test_관측_실패에_예외_메시지를_남길_자리가_없다(obs):
    """★★★ 「메시지는 넣지 마세요」라고 호출부에 부탁하는 대신 **넣을 자리를 없앴다.**

    ⚠️ 예외는 자주 입력값을 그대로 문자열에 담는다(`ValueError(f"…{payload}…")`).
      남기는 것은 «어느 행동에서 · 무슨 종류» 까지다."""
    obs.error(action="read", exc_type="ValueError")
    row = obs._rows()[0]
    assert (row["action"], row["path"]) == ("read", "ValueError")

    obs.reset()
    #: 예외 종류 자리에 값을 밀어 넣어 본다 — 영문자만 남는다.
    obs.error(action="주민번호 900101-1234567", exc_type="Error 900101-1234567 홍길동")
    row = obs._rows()[0]
    assert "1234567" not in str(row) and "홍길동" not in str(row), f"값이 남았다: {row}"
    assert row["action"] == "", "행동 자리가 자유 문자열이 됐다"


def test_기록_자리는_길이_상한이_있다(obs):
    """⚠️ 상한이 없으면 한 줄이 텔레메트리를 잡아먹고, 그 줄에는 대개 값이 들어 있다."""
    obs.observe(path="p" * 500, action="read", old_allowed=True, new_allowed=True,
                actor="u" * 500, resource_id="r" * 500, op="data.list")
    row = obs._rows()[0]
    for k in ("path", "actor", "resource_id"):
        assert len(row[k]) <= 96, f"{k} 가 {len(row[k])}자다"


# ── ⑧ 회차 구분 ──────────────────────────────────────────────────────────

def test_카나리_회차를_구분해_셀_수_있다(obs, monkeypatch):
    """★ 격리 카나리의 표본과 평상 트래픽을 섞어 세면 「그 시나리오를 정말 눌러 봤는가」에
    답할 수 없다."""
    monkeypatch.setenv("AFS_SHADOW_RUN", "canary_1")
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=True, op="data.list")
    monkeypatch.delenv("AFS_SHADOW_RUN")
    obs.observe(path="p", action="read", old_allowed=True, new_allowed=True, op="data.list")
    assert obs.switch_gate()["counts"]["total"] == 2
    assert obs.switch_gate("canary_1")["counts"]["total"] == 1
