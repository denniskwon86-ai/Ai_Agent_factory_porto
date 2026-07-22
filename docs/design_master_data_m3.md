# M3 상세 설계 — MCP 데이터 브로커 (Virtual Integration Broker)

> 작성: 2026-07-22 | 상태: **설계 확정(구현 착수 — 열린 질문 a~e 승인 완료)** | 선행: M1·M2(구현 완료)
> 근거: AI_HANDOFF §2-3 "연계 축" 최종 단계. "전체 복제가 아니라 메타+키맵만 복제, 데이터는 MCP
> 온디맨드 조회 + TTL 캐시(가상 통합)".

---

## 0. 한 줄 정의

M3 는 **M2 의 승인된 크로스워크(주소록)를 이용해, 외부 시스템의 실제 값을 필요할 때만 MCP 로 조회해
'가상 통합'하는 읽기 전용 브로커**다. 데이터를 우리 DB 로 복제하지 않는다 — 조회 결과를 짧게 캐시할 뿐.

## 1. 목적과 설계 원칙

**목적**: M1(우리 기준값) + M2(외부 매핑) 위에서, "이 골든 레코드의 **외부 실제값**은 지금 얼마인가"를
온디맨드로 answer 한다. 예: `PROC-ASSY-01` 의 표준리드타임은 M1 골든값 72h 지만, MES 실측은 지금 68h.

**원칙**:
1. **가상 통합(복제 금지).** 트랜잭션/대량 데이터를 우리 DB 에 적재하지 않는다. `mcp_cache` 는 조회
   결과의 **단기 TTL 캐시**일 뿐이며 진실원본이 아니다(원칙 = M1 "트랜잭션 저장 금지"의 연장).
2. **읽기 전용부터.** M3 v1 은 조회만. 쓰기(외부 시스템 갱신)는 범위 밖(후일, scope=read-write + 승인).
3. **재현성(as-of).** 모든 조회 결과에 `as_of`(조회 시각) 스탬프. 시뮬레이션이 외부값을 쓰면 그 `as_of`
   를 산출물에 함께 기록해, 나중에 "그때 그 값으로" 재현 가능하게 한다.
4. **비신뢰 입력.** MCP 로 들어온 값·문자열은 지식팩·M1 과 동일하게 **인젝션 방어**(자료로만, 지시 금지)
   대상. 컨텍스트 주입 시 방어 머리말 포함.
5. **승인 매핑만.** `key_crosswalk.confirmed=1` 이고 시스템 `status=active` 인 매핑만 조회 대상.

## 2. 아키텍처 흐름

```
[요청] 에이전트/ContextEngine/시뮬레이터
   → broker.resolve(master_code, system_id?)              # 무엇을·어디서
   → M2 조회: key_crosswalk(external_key) + external_schemas(mapped_attr = 어느 필드→어느 속성)
   → mcp_cache 확인 (TTL 유효?) ──유효──▶ 캐시값 반환(as_of 포함)
                              └─만료/없음─▶ MCP 온디맨드 조회(mcp_endpoint, 읽기전용)
                                            → 결과 정규화 + as_of 스탬프 → mcp_cache 저장 → 반환
```

- 브로커는 **값을 해석/판단하지 않는다**. 외부 필드값을 우리 속성명으로 라벨링해 그대로 전달할 뿐.

## 3. 데이터 모델 — `master.db` 확장 (또는 별도 `mcp_cache.db`)

```sql
-- 온디맨드 조회 결과의 단기 캐시(진실원본 아님). 복제가 아니라 '최근 조회값 메모'.
CREATE TABLE IF NOT EXISTS mcp_cache (
    system_id    TEXT NOT NULL,
    external_key TEXT NOT NULL,          -- M2 승인 매핑의 external_key ("entity:field=value")
    payload      TEXT NOT NULL,          -- 조회 결과 JSON (정규화된 필드→값)
    as_of        TEXT NOT NULL,          -- 조회 시각(ISO) — 재현성 기준
    ttl_sec      INTEGER DEFAULT 300,    -- 이 항목의 TTL
    PRIMARY KEY (system_id, external_key)
);
```

- 캐시 히트 판정: `now - as_of < ttl_sec`. 만료 시 재조회. **쓰기 없음**(읽기 전용).
- 시뮬 재현: 시뮬 산출물에 `{master_code, system_id, external_key, value, as_of}` 를 함께 저장.

## 4. 조회 인터페이스 — `core/mcp_broker.py`

| 함수 | 설명 |
|---|---|
| `resolve(master_code, system_id=None) -> dict` | 골든 레코드의 외부 실제값 조회(캐시 우선). system_id 미지정 시 활성 매핑 전체 |
| `resolve_batch(master_codes, system_id) -> list` | 다건 |
| `invalidate(system_id, external_key=None)` | 캐시 강제 만료(수동 새로고침) |
| `get_master_context_live(state)` | (선택) M1 주입 블록에 '외부 실측값(as_of)'을 병기 |

**API** `api/routes/mcp_control.py`, prefix `/api/v1/mcp`: `POST /resolve`, `POST /invalidate`,
`GET /systems/{id}/health`(MCP 연결 점검). 실제 MCP 호출은 어댑터(아래 §9-a) 뒤에 둔다.

## 5. 캐시·TTL·as-of 정책
- 기본 TTL 300초(시스템/엔티티별 오버라이드 가능 — `external_systems` 에 `default_ttl_sec` 추가 고려).
- 캐시 미스·MCP 실패 시: **정직한 실패**(빈값·에러 표식) — 옛 캐시를 무한 연장하지 않는다. M1 골든값으로
  자동 대체하지 않음(기준값과 실측값은 의미가 다르므로 혼동 금지).
- as_of 는 항상 반환·기록. 시뮬 재현 시 필수.

## 6. 보안·거버넌스
- **읽기 전용**(scope=read 강제; read-write 는 v2 + 별도 승인).
- **자격증명 비저장**: `external_systems.auth_ref` 는 실제 비밀이 아니라 **참조 키**(예: env 변수명·시크릿
  매니저 키). 실 비밀은 M3 가 저장/로그하지 않는다(코드에 값 유입 금지).
- MCP 유입 데이터 = 비신뢰: 주입 시 인젝션 방어 머리말, PII 최소화(필요 필드만).
- 감사: 조회 이력(system_id, external_key, as_of, 성공여부)을 텔레메트리에 남겨 오남용 탐지.

## 7. 연동 지점
- **ContextEngine**: 옵션 플래그로 '외부 실측값 병기'(기본 off — 쿼터·지연·신뢰 고려). M1 골든값은 항상,
  실측값은 명시적 요청 시.
- **시뮬레이터**: 파라미터를 M3 실측값으로 시딩할 때 `as_of` 를 산출물에 기록(전략3 폐쇄루프의 재현성).
- **M1 승격 루프**: 검증된 실측/시뮬값을 사용자 승인 후 M1 골든 레코드 '개정'으로 승격(기존 개정 규칙).

## 8. 구현 체크리스트(설계 확정 후)
1. `mcp_cache` DDL(master_data 소유) + `core/mcp_broker.py`(resolve·캐시·as_of)
2. **MCP 어댑터 인터페이스**(§9-a 결정 반영) — 실제 MCP 클라이언트 vs 목 어댑터
3. `api/routes/mcp_control.py` + main.py 등록
4. 보안(읽기전용·auth_ref 참조·비신뢰 주입) + 감사 로그
5. 테스트: 목 어댑터로 resolve→캐시히트→만료재조회→invalidate→실패 정직성
6. (선택) ContextEngine 실측 병기 토글, 시뮬 as_of 기록

## 9. 확정된 결정 (2026-07-22 사용자 승인)
- **(a) ✅ 어댑터 인터페이스 + 목(mock) 어댑터로 시작.** `MCPAdapter` 추상 뒤에 조회를 두고 v1 은
  `MockMCPAdapter` 로 로직·캐시·보안·as-of 를 굳힌다. 실 MCP 커넥터는 교체 가능(어댑터 교체만).
- **(b) ✅ 별도 `data/mcp_cache.db`.** master.db 와 분리(런타임 성격). gitignore. `mcp_broker` 소유.
- **(c) ✅ 순수 온디맨드(pull).** 사전 프리페치 없음 — 요청 시 캐시 확인→미스면 조회.
- **(d) ✅ ContextEngine 실측 병기 기본 off.** 명시 요청 시만. 매 LLM 호출에 외부 지연·쿼터·신뢰
  리스크를 얹지 않는다. M1 골든값은 항상, 실측은 옵트인.
- **(e) ✅ v1 읽기 전용 확정.** 쓰기(read-write)는 별도 설계로 분리(범위 밖).

착수 준비 완료 — 위 결정 반영본으로 M3 구현.

---

## 10. 다음
위 (a)~(e) 결정 후 구현 착수. M3 는 "모든 구현" 로드맵의 마지막 축이며, 완료 후 **A-1 완주 재실행**
(사용자 지정 최종 단계)으로 이동.
