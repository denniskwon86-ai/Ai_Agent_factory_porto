"""레버B — per-model 쿨다운 + 체인 정제 단위 테스트. LLM 0콜(게이트웨이 인스턴스 로직만)."""
import time
import types

import core.llm_gateway as g


def _bare_gateway():
    """네트워크/모델 인스턴스 없이 쿨다운 로직만 시험하기 위한 최소 게이트웨이 스텁."""
    gw = g.LLMGateway.__new__(g.LLMGateway)   # __init__ 우회(모델 생성 회피)
    gw._model_cooldown = {}
    # (name, instance) — instance 는 로직상 안 쓰이므로 sentinel
    gw._pro_chain = [("gemini-2.5-pro", object()), ("grok-2-latest", object()),
                     ("llama-3.3-70b-versatile", object())]
    return gw


# ── 체인 정제(비-텍스트 모델 제외) ───────────────────────────────────────────
def test_is_text_gen_model_filters_non_text():
    assert g._is_text_gen_model("gemini-2.5-pro") is True
    assert g._is_text_gen_model("gemini-2.5-pro-preview-tts") is False
    assert g._is_text_gen_model("gemini-3-pro-image") is False
    assert g._is_text_gen_model("lyria-3-pro-preview") is False
    assert g._is_text_gen_model("imagen-3.0") is False


# ── per-model 쿨다운 ─────────────────────────────────────────────────────────
def test_update_cooldowns_success_marks_prior_failures():
    gw = _bare_gateway()
    # gemini 실패 → grok 성공
    gw._update_cooldowns(["gemini-2.5-pro", "grok-2-latest"], ok=True)
    assert "gemini-2.5-pro" in gw._model_cooldown       # 앞선 실패 → 쿨다운
    assert "grok-2-latest" not in gw._model_cooldown    # 성공 모델 → live


def test_update_cooldowns_all_fail():
    gw = _bare_gateway()
    gw._update_cooldowns(["gemini-2.5-pro", "grok-2-latest", "llama-3.3-70b-versatile"], ok=False)
    assert gw._all_cooled(gw._pro_chain) is True         # 전부 실패 → 티어 소진


def test_live_names_excludes_cooled():
    gw = _bare_gateway()
    gw._model_cooldown["gemini-2.5-pro"] = time.time() + 999
    live = gw._live_names(gw._pro_chain)
    assert "gemini-2.5-pro" not in live and "grok-2-latest" in live


def test_cooldown_expires():
    gw = _bare_gateway()
    gw._model_cooldown["gemini-2.5-pro"] = time.time() - 1   # 이미 만료
    assert "gemini-2.5-pro" in gw._live_names(gw._pro_chain)  # 만료 → 재사용 가능


def test_all_cooled_triggers_when_every_model_down():
    gw = _bare_gateway()
    now = time.time() + 999
    for n, _ in gw._pro_chain:
        gw._model_cooldown[n] = now
    assert gw._all_cooled(gw._pro_chain) is True


def test_success_clears_prior_cooldown():
    gw = _bare_gateway()
    gw._model_cooldown["grok-2-latest"] = time.time() + 999   # 이전에 죽었던 grok
    gw._update_cooldowns(["grok-2-latest"], ok=True)          # 이번엔 grok 성공
    assert "grok-2-latest" not in gw._model_cooldown          # 부활(쿨다운 해제)


def test_config_params_present():
    import config
    assert config.MAX_GEMINI_VARIANTS >= 1
    assert config.MODEL_COOLDOWN_SEC > 0
    assert config.QUOTA_RETRY_SLEEP_SEC >= 0
