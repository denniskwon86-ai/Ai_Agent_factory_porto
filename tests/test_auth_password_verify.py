# -*- coding: utf-8 -*-
"""★★★ 비밀번호 대조 — **한글 비밀번호가 서버를 죽였다**(2026-08-23 실측).

## 무엇을 잡는 시험인가

`hmac.compare_digest` 는 `str` 인자를 받을 때 **ASCII 만** 허용한다. 비ASCII 가 한 글자라도
있으면 `TypeError` 로 터진다. 그래서 로그인 화면에 한글 비밀번호를 넣으면 «비밀번호가
틀렸습니다»(401) 가 아니라 **500 Internal Server Error** 가 났다.

★ 한국어 사용 기업에서 이것은 예외 상황이 아니라 **기본 경로**다. 그리고 로그인 화면은
  인증 없이 누구나 두드릴 수 있는 곳이다 — 거기서 나는 500 은 사용자에게 「내 계정이
  고장났나」로 보이고, 로그에는 스택 트레이스가 쌓인다.

⚠️ 이 시험은 «틀린 비밀번호가 거부되는가» 를 보는 것이 **아니다**(그건 원래 초록이었다).
  «틀린 비밀번호가 **거부로** 끝나는가, 아니면 **폭발**하는가» 를 본다. 그 둘을 가르지
  않으면 500 이 「막혔다」로 집계된다.
"""
import os

import pytest

from core.auth import DEFAULT_PASSWORD, AuthStore


@pytest.fixture()
def store(tmp_path):
    """파일 경계로 격리한다 — 운영 `data/auth.db` 를 건드리지 않는다.

    ⚠️ `TemporaryDirectory()` 를 쓰지 않는다. `AuthStore` 는 `with self._connect()` 로
      **커밋만 하고 닫지 않으므로**(sqlite3 컨텍스트 매니저의 의미) Windows 에서 파일이
      잠긴 채 남고, 정리 단계가 `PermissionError` 로 터진다. 시험은 14건 통과 + 14건
      **오류**가 되고, 요약만 보면 초록으로 읽힌다."""
    return AuthStore(db_path=os.path.join(str(tmp_path), "auth.db"))


#: 저장된 해시가 **없는** 계정(= 공통 초기값과 대조하는 경로)과 **있는** 계정 양쪽을 본다.
#: 결함은 앞쪽 경로에만 있었지만, 뒤쪽도 같은 입력을 받으므로 함께 고정한다.
NON_ASCII = ["비밀번호1", "pass1로변경", "contraseña", "пароль", "🔑key", "パスワード"]


@pytest.mark.parametrize("pw", NON_ASCII)
def test_non_ascii_password_is_rejected_not_crashed(store, pw):
    """비ASCII 비밀번호는 **False 를 돌려준다.** 예외를 던지지 않는다."""
    assert store.verify("hikwon@lsmnm.com", pw) is False


@pytest.mark.parametrize("pw", NON_ASCII)
def test_non_ascii_password_survives_stored_hash_path(store, pw):
    """자기 비밀번호를 저장한 계정에서도 같다."""
    store.set_password("hikwon@lsmnm.com", "somethingelse")
    assert store.verify("hikwon@lsmnm.com", pw) is False


def test_non_ascii_password_can_actually_be_used(store):
    """★ 거부만 하면 반쪽이다 — **한글 비밀번호로 실제 로그인이 되어야 한다.**

    ⚠️ 「비ASCII 는 안전하게 거부된다」로 끝내면 통제가 아니라 **기능 결손**이다.
      비밀번호를 한글로 바꾼 사용자는 자기 계정에 영원히 못 들어간다."""
    store.set_password("hikwon@lsmnm.com", "한글비밀번호")
    assert store.verify("hikwon@lsmnm.com", "한글비밀번호") is True
    assert store.verify("hikwon@lsmnm.com", "한글비밀번호 ") is False


def test_default_password_still_works(store):
    """공통 초기값 경로는 그대로 산다(회귀 방지)."""
    assert store.verify("hikwon@lsmnm.com", DEFAULT_PASSWORD) is True
    assert store.verify("hikwon@lsmnm.com", DEFAULT_PASSWORD + "x") is False
    assert store.verify("", DEFAULT_PASSWORD) is False
    assert store.verify("hikwon@lsmnm.com", "") is False
