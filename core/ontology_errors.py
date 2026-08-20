"""★ 온톨로지 예외 — **아무것도 import 하지 않는 가장 아래 층.**

## 왜 별도 모듈인가

`ontology_resolvers` 는 `OntologyResolverError` 를 던져야 하고, `ontology_runtime` 은
그것을 잡아 503 으로 바꿔야 한다. 그런데 resolvers 는 runtime 의 `ObjectRef` 를 쓰고
runtime 은 resolvers 의 함수를 쓴다 — 예외를 어느 한쪽에 두면 **순환 참조**가 된다
(2026-08-20 실측: 실제로 났다).

⚠️ 지연 import 로 우회할 수도 있지만, 그러면 「왜 여기만 함수 안에서 import 하나」를
  다음 사람이 매번 다시 판단해야 한다. 층을 하나 만드는 편이 싸다.

LLM 0콜.
"""
from __future__ import annotations


class OntologyResolverError(RuntimeError):
    """★★★ **저장소 장애·미배선** — 「보이지 않는다」와 다른 사실이다.

    ⚠️⚠️ [2026-08-20 Supervisor 지적 P0-3] 종전에는 Resolver 가 저장소 오류까지 전부
      `None` 으로 접었고, 런타임은 그것을 「이 문맥에서 안 보이는 객체」로 읽어 **경로를
      조용히 지웠다.** 그러면 화면은 「영향 경로 없음」을 그리고 사용자는 그것을 **사실**로
      읽는다 — 이 저장소가 화면 전체에서 지켜 온 «조회 실패 ≠ 0건» 이 온톨로지에서만
      무너지는 것이다.

    ★ 그래서 갈라 둔다:
        · 미존재·권한 밖   → `None`  (경로에서 지운다. 존재를 누설하지 않는다)
        · 저장소 장애·미배선 → 이 예외 (런타임이 `OntologyIntegrityError` → **503**)
    """
