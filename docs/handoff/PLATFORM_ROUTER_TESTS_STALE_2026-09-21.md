# 알림 — 라우터는 정상입니다. **시험이 낡았습니다** (10 건)

- 기준일: 2026-09-21
- 보내는 쪽: 확산 적용 사전 검토 (`claude/diffusion-readiness-20260916`)
- ⚠️ **플랫폼 코드는 건드리지 않았습니다.** 원인을 밝혀 전달만 합니다
- 이 문서의 숫자는 전부 실행해서 얻은 것입니다

---

## 0. 결론부터

`tests/` 전체에서 **11 건이 실패**하는데, 그중 **10 건이 같은 원인**입니다. 그리고
그 원인은 **기능 결함이 아닙니다.**

    GET /api/v1/health                    → 200
    GET /api/v1/data-preparation/kits     → 200      ← 실제로 돕니다
    OpenAPI 경로 464 개 (data-preparation 21 개)

**라우터는 제대로 붙어 있습니다.** 시험이 라우터를 찾는 **방법**이 지금 FastAPI 에서
통하지 않을 뿐입니다.

★ `main.py` 의 주석은 「라우터가 앱에 붙지 않으면 그 기능은 **시험에서만** 존재한다」고
  경고합니다. 지금은 **정반대**입니다 — 기능은 있는데 **시험이 그것을 보지 못합니다.**

---

## 1. 무슨 일인가

시험들은 이렇게 경로를 모읍니다.

```python
have = {(m, r.path) for r in main.app.routes
        for m in (getattr(r, "methods", None) or ())}
```

그런데 FastAPI 0.139 에서 `include_router()` 는 **`_IncludedRouter` 객체**를
`app.routes` 에 넣고, 실제 경로는 그 안에 들어 있습니다.

| 실측 | |
|---|---|
| `app.routes` 중 `methods` 가 있는 것 | **5 개** (health · docs · openapi …) |
| `_IncludedRouter` 로 남은 것 | **45 개** — `include_router` 전부 |
| `app.router.routes` | 같음 (5 개) |
| `_IncludedRouter.effective_candidates` | **50 개** — 여기에 실제 라우트가 있다 |
| `app.openapi()["paths"]` | **464 경로 · 540 (method, path)** |

즉 `getattr(r, "methods", None)` 이 전부 `None` 이 되어 **빈 집합**이 만들어지고,
무엇을 찾든 「없다」가 됩니다.

---

## 2. 영향받는 시험 10 건

    tests/test_host_runtime_wire.py::test_계약이_가리키는_경로가_실제로_서버에_있다
    tests/test_ontology_namespace_capabilities.py::test_runtime_status_route_is_mounted_on_the_product_router
    tests/test_ownership_api.py::test_제품_앱에_소유권_경로가_붙어_있다
    tests/test_planning_driver_release.py::test_product_routes_are_mounted
    tests/test_planning_scenario_release.py::test_product_router_exposes_human_approval_and_revocation_paths
    tests/test_research_recommender.py::test_the_routes_are_registered
    tests/test_router_registration.py::test_every_router_is_mounted
    tests/test_router_registration.py::test_the_pilot_paths_are_reachable[/api/v1/data-preparation]
    tests/test_router_registration.py::test_the_pilot_paths_are_reachable[/api/v1/baseline]
    tests/test_router_registration.py::test_the_pilot_paths_are_reachable[/api/v1/appdata/runtime]

⚠️ 나머지 1 건(`test_seed_starter_data_refresh`)은 **다른 원인**입니다 —
[키트 1.2.0 알림](KIT_VERSION_1_2_0_NOTICE_2026-09-17.md) 2.2 를 보십시오.

---

## 3. 고치는 법 — **OpenAPI 로 모읍니다**

```python
spec = main.app.openapi()
have = {(m.upper(), p) for p, ops in spec.get("paths", {}).items() for m in ops}
assert ("POST", "/api/v1/data-preparation/ownership/approve") in have
```

실제로 돌려 확인했습니다 — 시험들이 찾던 경로가 **전부 여기 있습니다.**

    POST  /api/v1/data-preparation/ownership/approve    있다
    GET   /api/v1/data-preparation/ownership            있다

| 안 | 판단 |
|---|---|
| **`app.openapi()["paths"]`** | ✅ **권장.** 공개 API 이고, 「사용자가 실제로 부를 수 있는 경로」와 뜻이 같다 |
| `_IncludedRouter.effective_candidates` | ✗ 밑줄로 시작하는 **내부 구현**이다. 다음 판에 사라질 수 있다 |
| `TestClient` 로 요청해 404 가 아닌지 | △ 가장 정직하지만 느리고, 권한·본문 때문에 200 이 아닐 수 있다 |

⚠️ OpenAPI 에 안 잡히는 라우트도 있습니다(`include_in_schema=False`). 그런 경로를
  검사하는 시험은 `TestClient` 쪽이 맞습니다.

---

## 4. 이것이 아닙니다 — 확인한 것

| | |
|---|---|
| 우리(확산 검토)의 변경 때문인가 | **아닙니다.** `include_router` **45 개 전부**가 그렇습니다 — 파일 하나로 그럴 수 없습니다 |
| `main.py` 가 바뀌었나 | **아닙니다** (2026-09-17 이후 변경 없음) |
| 그 시험 파일들이 바뀌었나 | **아닙니다** (같은 기간 변경 없음) |
| FastAPI 를 최근 올렸나 | **아닙니다** — 0.139.0 이 **2026-07-15** 설치입니다 |
| 시험 순서 탓인가 | **아닙니다.** 단독으로도, 앱을 띄우는 시험을 앞에 둬도 실패합니다 |

★ 그러면 **언제부터인가**는 저희가 답할 수 없습니다. 다만 FastAPI 설치일(7 월)과
  이 시험들이 쓰인 시점 사이 어디쯤일 것입니다.

⚠️ 저희가 2026-09-17 에 잰 「기준선」에는 이 10 건 중 일부가 안 보였는데, 그것은
  출력을 `| tail -8` 로 잘라 **앞쪽이 사라졌기 때문**입니다. 그때도 실패하고
  있었습니다.

---

## 5. 왜 급한가

이 시험들이 지키려던 것은 **「만들어 놓고 등록하지 않았다」** 였습니다 — `main.py`
주석에 그 사고가 적혀 있습니다(2026-08-19).

지금은 그 감시가 **꺼져 있는 것과 같습니다.** 전부 실패 상태라 **진짜로 라우터를
빠뜨려도 아무도 모릅니다.** 고치면 그 방어가 되살아납니다.

---

## 6. 재현

```bash
# 라우터가 실제로 도는지
python -c "from fastapi.testclient import TestClient; import main; \
print(TestClient(main.app).get('/api/v1/data-preparation/kits').status_code)"

# app.routes 가 무엇을 담고 있는지
python -c "import main; \
print(sum(1 for r in main.app.routes if hasattr(r,'methods')), '/', len(main.app.routes))"

# 실패 목록
python -m pytest tests/ -q --tb=no > 결과.txt 2>&1
```

⚠️ 출력을 `| tail` 로 자르지 마십시오. `FAILED` 는 알파벳 순이라 **앞쪽이 잘립니다.**
