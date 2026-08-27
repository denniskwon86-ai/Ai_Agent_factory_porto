"""★★★ OpenRouter 전용 모드 — **다른 제공사를 만들지도 않는다.** (2026-08-27 한시 조치)

## 왜 생겼나

실측(`TEST001` 재빌드 199콜 / 73분): 폴백 실패 190건 중 **429 무료 쿼터 소진 130건**.
병목은 제공사 속도가 아니라 무료 티어 일일 쿼터였다. 그리고 무료 체인이 소진되면 남는
것이 출력 8k 짜리 llama 뿐이라 구조화 코드 생성이 **구조적으로** 실패한다(결함 #15).

## ⚠️⚠️ 왜 리스트를 바꾸는 것으로 안 되나

`LLM_*_FALLBACK_LIST` 는 **위치가 곧 제공사**다:

    [0]=Gemini  [1]=xAI  [2]=Groq  [3]=Cerebras  [4]=OpenRouter

`llm_gateway` 가 인덱스로 제공사 생성자를 고르므로, 다섯 칸을 OpenRouter 슬러그로
채우면 **Groq 에 OpenRouter 슬러그를 보내는 체인**이 만들어진다. 실제로 한 번 그랬고
그 사고가 `config.py` 주석에 남아 있다. 그래서 **별도 리스트 + 별도 갈래**로 둔다.

## 이 파일이 지키는 것

  ① 켜면 체인에 OpenRouter 아닌 모델이 **한 개도 없다**
  ② 끄면 종전 체인이 **그대로다**(한시 조치가 기존 동작을 바꾸지 않는다)
  ③ 키가 없으면 **멈춘다** — 조용히 무료 체인으로 되돌아가지 않는다
  ④ `:free` 슬러그를 **거부한다**
  ⑤ 환경변수가 config 를 이긴다 — 코드를 안 고치고 되돌릴 수 있어야 한다

★ ①②는 **대조군이 진짜 대조군인지**를 함께 본다. 한쪽만 보면 「전부 OpenRouter」로
  고쳐 놓아도 초록이 된다.
"""
import pytest

from core import llm_gateway as gw


# ── ⑤ 스위치 자체 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("on", True), ("YES", True),
    ("0", False), ("false", False), ("off", False), ("no", False),
])
def test_환경변수가_config_를_이긴다(monkeypatch, raw, expected):
    """★ 켜는 쪽도 **끄는 쪽도** 환경변수로 된다.

    ⚠️ 끄는 방향이 없으면, 되돌리려고 서버 코드를 고치게 되고 그 수정이 남는다."""
    monkeypatch.setenv("AFS_OPENROUTER_ONLY", raw)
    #: config 를 **반대로** 놓고도 환경변수가 이기는지 본다
    monkeypatch.setattr(gw.config, "OPENROUTER_ONLY", not expected, raising=False)
    assert gw._openrouter_only() is expected


def test_환경변수가_없으면_config_를_따른다(monkeypatch):
    monkeypatch.delenv("AFS_OPENROUTER_ONLY", raising=False)
    monkeypatch.setattr(gw.config, "OPENROUTER_ONLY", True, raising=False)
    assert gw._openrouter_only() is True
    monkeypatch.setattr(gw.config, "OPENROUTER_ONLY", False, raising=False)
    assert gw._openrouter_only() is False


# ── ④ 무료 슬러그 거부 ───────────────────────────────────────────────────

def test_free_슬러그를_거부한다():
    """★★★ `:free` 는 OpenRouter 를 거친 **무료 쿼터**다 — 이 모드가 없애려는 것 자체.

    ⚠️ 크레딧이 있어도 무료 쿼터에 묶여 실패한다(2026-07-26 실측)."""
    with pytest.raises(RuntimeError) as e:
        gw._openrouter_only_chain("Pro", ["google/gemini-2.0-flash-lite-preview-02-05:free"])
    assert "무료" in str(e.value)


def test_빈_체인을_거부한다():
    """⚠️ 빈 체인으로 뜨면 첫 호출에서야 실패한다 — 그때는 이미 프로젝트가 돌고 있다."""
    with pytest.raises(RuntimeError):
        gw._openrouter_only_chain("Pro", [])


def test_등록된_슬러그는_통과한다():
    """★ 대조군 — 거부 규칙이 정상 슬러그까지 막으면 이 모드는 못 쓴다."""
    out = gw._openrouter_only_chain("Pro", ["google/gemini-2.5-flash"])
    assert out == ["google/gemini-2.5-flash"]


def test_가격_미등록은_막지_않고_경고한다(capsys):
    """⚠️ 막으면 슬러그를 바꾸려는 사람이 여기서 걸리고, 그러면 이 스위치를 안 쓴다.
    ★ 다만 조용히 넘어가지도 않는다 — 미등록이면 **과금 산정이 0 으로 빈다.**"""
    out = gw._openrouter_only_chain("Pro", ["openai/some-unregistered-model"])
    assert out == ["openai/some-unregistered-model"]
    assert "LLM_PRICE_PER_MTOK" in capsys.readouterr().out


# ── ③ fail-closed ────────────────────────────────────────────────────────

def test_키가_없으면_멈춘다(monkeypatch):
    """★★★ **조용히 무료 체인으로 되돌아가지 않는다.**

    ⚠️⚠️ 되돌리면 사용자는 「OpenRouter 로 돌린다」고 믿으면서 정확히 없애려던 429
      폭풍을 다시 맞는다. 그리고 로그만 보고는 알 수 없다 — 거기 찍히는 gemini 이름은
      켜졌을 때도 찍히는 이름이기 때문이다."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as e:
        gw._assert_openrouter_only_usable()
    assert "OPENROUTER_API_KEY" in str(e.value)


def test_패키지가_없으면_멈춘다(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(gw, "_OPENROUTER_AVAILABLE", False, raising=False)
    with pytest.raises(RuntimeError) as e:
        gw._assert_openrouter_only_usable()
    assert "langchain-openai" in str(e.value)


def test_키가_있으면_통과한다(monkeypatch):
    """★ 대조군 — 이것이 없으면 위 둘은 「항상 예외」만 증명한다."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(gw, "_OPENROUTER_AVAILABLE", True, raising=False)
    gw._assert_openrouter_only_usable()


# ── ①② 체인이 실제로 갈리는가 ───────────────────────────────────────────

def _chain_names(monkeypatch, on: bool):
    monkeypatch.setenv("AFS_OPENROUTER_ONLY", "1" if on else "0")
    g = gw.LLMGateway()
    return ([n for n, _ in g._pro_chain], [n for n, _ in g._flash_chain],
            {type(i).__name__ for _, i in g._pro_chain + g._flash_chain})


def test_켜면_OpenRouter_아닌_모델이_하나도_없다(monkeypatch):
    """★★★ **이 파일의 요지.**

    ⚠️ 이름만 보지 않는다 — **인스턴스 타입**까지 본다. 이름이 OpenRouter 슬러그인데
      Groq 클라이언트에 실려 있으면(위 주석의 그 사고) 이름 검사만으로는 초록이다."""
    pro, flash, types = _chain_names(monkeypatch, on=True)
    bad = [n for n in pro + flash if not n.startswith(("google/", "openai/",
                                                       "anthropic/", "meta-llama/"))]
    assert not bad, f"OpenRouter 슬러그가 아닌 모델이 남았다: {bad}"
    assert types == {"ChatOpenAI"}, f"OpenRouter 클라이언트가 아닌 인스턴스: {types}"


def test_끄면_종전_체인_그대로다(monkeypatch):
    """★★★ 대조군. 한시 조치가 **기존 동작을 바꾸면** 끄고도 못 돌아간다."""
    pro, flash, types = _chain_names(monkeypatch, on=False)
    assert any(n.startswith("gemini") for n in pro), f"Gemini 가 사라졌다: {pro}"
    assert len(types) > 1, f"제공사가 하나뿐이다 — 끈 게 아니다: {types}"
