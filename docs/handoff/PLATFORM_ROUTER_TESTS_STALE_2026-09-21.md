# 라우터는 정상입니다. **시험이 낡았습니다** — ✅ 고쳤습니다 (10 건)

- 기준일: 2026-09-21
- 보내는 쪽: 확산 적용 사전 검토 (`claude/diffusion-readiness-20260916`)
- **상태: 고쳤습니다.** 처음에는 원인만 전달하려 했으나 요청을 받아 시험을 고쳤습니다
- ⚠️ **고친 것은 `tests/` 뿐입니다.** `main.py`·`api/`·라우터는 건드리지 않았습니다 —
  애초에 거기에는 문제가 없었습니다
- 이 문서의 숫자는 전부 실행해서 얻은 것입니다

---

## ✅ 무엇을 고쳤나 (2026-09-21)

`tests/conftest.py` 에 **공통 헬퍼**를 두고 열 곳이 그것을 쓰게 했습니다. 다음에
FastAPI 가 또 바뀌어도 **한 곳만** 고치면 됩니다.

```python
app_endpoints(app)   # {(METHOD, path)}  — 548 개
app_paths(app)       # {path}            — 468 개
```

`_IncludedRouter` 를 한 겹 펼치고, **그 내부 구현이 사라지면 `app.openapi()` 로
떨어집니다**(540 개 — 업무 경로는 전부, `/docs` 등 문서 경로 4 개만 빠집니다).

★ 고치다 **거짓 초록** 하나를 찾았습니다. `test_host_runtime_wire` 의

    bad = [r.path for r in app.routes if ...startswith(shape)]

가 **언제나 빈 목록**이라 통과하고 있었습니다 — 「데이터셋 없는 레코드 경로가
되살아나면 잡는다」는 감시가 꺼져 있었습니다. 실패 10 건에는 안 잡히던 것입니다.

고친 시험 **104 건 통과**.

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
| `_IncludedRouter` 펼치기 | **주 경로로 썼다.** 문서 경로까지 **전부**(548) 잡힌다. 다만 내부 구현이라 사라질 수 있다 |
| `app.openapi()["paths"]` | **폴백으로 썼다.** 공개 API 라 안전하지만 `include_in_schema=False` 인 4 개가 빠진다 |
| `TestClient` 로 요청해 404 가 아닌지 | △ 가장 정직하지만 느리고, 권한·본문 때문에 200 이 아닐 수 있다 |

★ **둘을 함께 쓴다.** 펼치기가 통하지 않으면(그 결과가 `app.routes` 수보다 작으면)
  스펙으로 떨어진다 — 내부 구현이 바뀌어도 시험이 조용히 빈손이 되지 않는다.

⚠️ 처음 이 문서를 쓸 때는 「OpenAPI 만 권장, 내부 구현은 쓰지 말 것」이라고 적었다.
  실제로 구현하면서 바꿨다 — 펼치기가 **문서 경로까지 보고**, 폴백을 두면 내부 구현
  위험이 상쇄되기 때문이다.

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

## 5. 왜 고쳐야 했나

이 시험들이 지키려던 것은 **「만들어 놓고 등록하지 않았다」** 였습니다 — `main.py`
주석에 그 사고가 적혀 있습니다(2026-08-19).

그 감시가 **꺼져 있었습니다.** 전부 실패 상태라 진짜로 라우터를 빠뜨려도 아무도
모르는 상태였고, 그보다 나쁜 것은 **통과하면서 아무것도 보지 않던 시험**이었습니다
(위 「거짓 초록」). 이제 되살아났습니다.

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
