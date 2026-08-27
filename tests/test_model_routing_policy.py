"""★★★ 모델 라우팅 정책 — **관리자가 화면에서 바꾼다.** (2026-08-27)

## 이 파일이 지키는 것

  ① 우선순위가 **한 곳에서만** 정해진다 — env > 저장소 > 코드 기본값
  ② 「환경변수 없음」과 「환경변수가 끄라고 함」을 **가른다**
  ③ 저장했는데 **안 먹는** 상태를 화면이 볼 수 있다(`source` · `overridden`)
  ④ 사유 없이는 **서버가 막는다**
  ⑤ 게이트웨이가 이 판정을 쓴다 — 두 곳에서 판정하지 않는다
  ⑥ 저장소가 깨져도 **멈추지 않는다**

## ⚠️⚠️ ④는 실측으로 생겼다

화면에만 `required` 를 걸고 서버에서 안 막았더니, API 를 직접 부르는 경로로 사유 없이
200 이 났고 **이력에 빈 사유 한 줄이 남았다.** 화면이 지키는 통제는 화면을 거치지 않는
순간 사라진다.

## ⚠️ ③이 왜 중요한가

환경변수가 저장소를 이기는 구조다. 값만 그리면 관리자가 스위치를 내리고 「껐다」고
믿는데 서버는 켜진 채로 돈다 — 그리고 화면만 보고는 알 수 없다.
"""
import json

import pytest

from core import model_routing_policy as mrp


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """⚠️⚠️ **운영 `data/` 를 열지 않는다.** 이 시험은 정책 파일을 쓴다."""
    monkeypatch.setattr(mrp, "_PATH", str(tmp_path / "model_routing_policy.json"),
                        raising=False)
    monkeypatch.delenv(mrp._ENV_KEY, raising=False)
    return tmp_path


# ── ①② 우선순위 ─────────────────────────────────────────────────────────

def test_아무것도_없으면_코드_기본값이다(monkeypatch):
    monkeypatch.setattr(mrp, "_code_default", lambda: True)
    e = mrp.effective()
    assert e["enabled"] is True and e["source"] == mrp.SOURCE_CODE


def test_저장소가_코드_기본값을_이긴다(monkeypatch):
    monkeypatch.setattr(mrp, "_code_default", lambda: True)
    mrp.set_openrouter_only(False, "admin@x", "비용 확인")
    e = mrp.effective()
    assert e["enabled"] is False and e["source"] == mrp.SOURCE_STORE


def test_환경변수가_저장소를_이긴다(monkeypatch):
    monkeypatch.setattr(mrp, "_code_default", lambda: False)
    mrp.set_openrouter_only(False, "admin@x", "껐다")
    monkeypatch.setenv(mrp._ENV_KEY, "1")
    e = mrp.effective()
    assert e["enabled"] is True and e["source"] == mrp.SOURCE_ENV


def test_환경변수_없음과_끄라고_함을_가른다(monkeypatch):
    """★★★ 여기서 `False` 로 뭉개면 저장소 값이 **영영 안 먹는다.**"""
    monkeypatch.delenv(mrp._ENV_KEY, raising=False)
    assert mrp._env_value() is None, "환경변수 없음이 None 이 아니다"
    monkeypatch.setenv(mrp._ENV_KEY, "0")
    assert mrp._env_value() is False, "«0» 이 None 으로 읽힌다"
    monkeypatch.setenv(mrp._ENV_KEY, "")
    assert mrp._env_value() is None, "빈 문자열이 값으로 읽힌다"


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("TRUE", True), ("on", True), ("yes", True),
    ("0", False), ("False", False), ("OFF", False), ("no", False),
    ("아무말", None), ("2", None),
])
def test_환경변수_표기를_모두_읽는다(monkeypatch, raw, expected):
    """⚠️ 모르는 값을 `True`/`False` 어느 쪽으로도 단정하지 않는다 — 오타 하나로
    모드가 뒤집히면 그 사실을 아무도 모른다."""
    monkeypatch.setenv(mrp._ENV_KEY, raw)
    assert mrp._env_value() is expected


# ── ③ 저장했는데 안 먹는 상태를 화면이 본다 ──────────────────────────────

def test_눌린_저장값을_화면이_알_수_있다(monkeypatch):
    """★★★ **이 파일의 요지.** 이것이 없으면 화면은 거짓을 그린다."""
    monkeypatch.setattr(mrp, "_code_default", lambda: False)
    mrp.set_openrouter_only(False, "admin@x", "껐다")
    monkeypatch.setenv(mrp._ENV_KEY, "1")
    e = mrp.effective()
    assert e["overridden"] is True, "저장값이 눌린 사실을 화면이 알 수 없다"
    assert e["stored_value"] is False and e["env_value"] is True
    assert e["source"] == mrp.SOURCE_ENV


def test_같은_값이면_눌렸다고_하지_않는다(monkeypatch):
    """★ 대조군 — 늘 `overridden=True` 면 화면이 항상 경고를 띄우고, 사람은 그것을
    무시하게 된다(그러면 진짜 충돌도 같이 무시된다)."""
    mrp.set_openrouter_only(True, "admin@x", "켰다")
    monkeypatch.setenv(mrp._ENV_KEY, "1")
    assert mrp.effective()["overridden"] is False


def test_저장한_적이_없으면_눌렸다고_하지_않는다(monkeypatch):
    monkeypatch.setenv(mrp._ENV_KEY, "1")
    e = mrp.effective()
    assert e["stored_value"] is None and e["overridden"] is False


# ── ④ 서버가 막는다 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("reason", ["", "   ", None])
def test_사유가_없으면_거부한다(reason):
    """⚠️⚠️ 화면에만 걸어 두면 API 직접 호출로 뚫린다 — 실제로 뚫렸다."""
    with pytest.raises(mrp.ModelRoutingError) as e:
        mrp.set_openrouter_only(False, "admin@x", reason)
    assert "사유" in str(e.value)


def test_행위자가_없으면_거부한다():
    with pytest.raises(mrp.ModelRoutingError):
        mrp.set_openrouter_only(False, "  ", "사유 있음")


def test_거부되면_아무것도_저장되지_않는다():
    """★★★ 「막혔다」와 「막혔는데 남았다」는 다르다."""
    with pytest.raises(mrp.ModelRoutingError):
        mrp.set_openrouter_only(False, "admin@x", "")
    assert mrp._stored() is None, "거부됐는데 값이 저장됐다"
    assert mrp.history() == [], "거부됐는데 이력이 남았다"


def test_사유가_있으면_통과한다():
    """★ 대조군 — 이것이 없으면 위 시험들은 「항상 거부」만 증명한다."""
    out = mrp.set_openrouter_only(True, "admin@x", "쿼터 소진 회피")
    assert out["enabled"] is True and out["actor"] == "admin@x"


# ── 이력·감사 ────────────────────────────────────────────────────────────

def test_이력에_바꾼_사람과_사유가_남는다():
    mrp.set_openrouter_only(True, "admin@x", "켠 이유")
    mrp.set_openrouter_only(False, "admin@y", "끈 이유")
    rows = mrp.history()
    assert rows[0]["actor"] == "admin@y" and rows[0]["reason"] == "끈 이유"
    assert rows[0]["to"] is False and rows[1]["to"] is True


def test_결과_문장이_양쪽_다_결과를_말한다():
    """⚠️ 한쪽만 위험한 것처럼 적으면 사람은 반대쪽을 «안전한 기본» 으로 읽는다."""
    on = mrp.set_openrouter_only(True, "admin@x", "r")["note"]
    off = mrp.set_openrouter_only(False, "admin@x", "r")["note"]
    assert "비용" in on
    assert "429" in off or "쿼터" in off


def test_결과_문장에_마크다운을_쓰지_않는다():
    """★★★ [화면 실측] `Banner` 는 평문을 그린다 — `**강조**` 가 별표째로 보였다.

    ⚠️ 서버가 화면의 렌더링 방식을 가정하면, 그 가정이 틀렸을 때 사용자가 별표를 읽는다."""
    for v in (True, False):
        note = mrp.set_openrouter_only(v, "admin@x", "r")["note"]
        assert "**" not in note, f"note 에 마크다운이 남아 있다: {note}"


# ── ⑤ 게이트웨이가 같은 판정을 쓴다 ─────────────────────────────────────

def test_게이트웨이가_이_판정을_쓴다(monkeypatch):
    """★★★ 두 곳에서 판정하면 「화면은 꺼졌다는데 게이트웨이는 켜진」 상태가 된다."""
    from core import llm_gateway as gw

    mrp.set_openrouter_only(True, "admin@x", "r")
    assert gw._openrouter_only() is True
    mrp.set_openrouter_only(False, "admin@x", "r")
    assert gw._openrouter_only() is False


def test_판독이_실패해도_게이트웨이가_멈추지_않는다(monkeypatch):
    """⚠️ 모델 라우팅이 설정 파일 하나 때문에 죽으면 안 된다."""
    from core import llm_gateway as gw

    monkeypatch.setattr(mrp, "enabled", lambda: (_ for _ in ()).throw(OSError("깨짐")))
    monkeypatch.setattr(gw.config, "OPENROUTER_ONLY", True, raising=False)
    assert gw._openrouter_only() is True          # 코드 기본값으로 되돌아간다


# ── ⑥ 깨진 저장소 ───────────────────────────────────────────────────────

def test_저장소가_깨져도_코드_기본값으로_돈다(monkeypatch, _isolated):
    with open(mrp._PATH, "w", encoding="utf-8") as f:
        f.write("{ 이건 JSON 이 아니다")
    monkeypatch.setattr(mrp, "_code_default", lambda: True)
    assert mrp.effective()["source"] == mrp.SOURCE_CODE
    assert mrp.enabled() is True


def test_저장소가_없어도_돈다(monkeypatch):
    monkeypatch.setattr(mrp, "_code_default", lambda: False)
    assert mrp.enabled() is False
    assert mrp.history() == []
