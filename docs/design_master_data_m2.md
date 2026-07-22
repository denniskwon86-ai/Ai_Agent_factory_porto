# M2 상세 설계 — 스키마 레지스트리 + 키 크로스워크 (Schema Registry & Key Crosswalk)

> 작성: 2026-07-22 | 상태: **설계 초안(검토 대기)** | 선행: M1(`docs/design_master_data_m1.md`, 구현 완료)
> 후속: M3 MCP 데이터 브로커. 근거: AI_HANDOFF §2-3 로드맵("연계 축").

---

## 0. 한 줄 정의

M2 는 **"우리 기준정보(M1 골든 레코드) ↔ 외부 연계 시스템의 키·필드"를 매핑하는 계층**이다.
매핑은 **LLM 이 초안을 제안하고 사람이 승인해야만 유효**(confirmed=1)하며, 승인 전 매핑은 절대 사용되지
않는다. M2 자체는 데이터를 복제하지 않는다 — 복제(온디맨드 조회)는 M3 의 역할이고, M2 는 그 **주소록**이다.

## 1. 목적과 설계 원칙

**목적**: 연계 시스템(ERP·MES·PLM·사내 DB 등)을 등록하고, 그 시스템의 스키마(엔티티/필드)를 받아,
우리 `master_records` 및 `entity_types` 와 **키/필드 대응표**를 만든다. 이후 M3 가 이 대응표를 이용해
외부 데이터를 온디맨드로 가상 통합한다.

**원칙**:
1. **매핑은 제안-승인 2단계.** LLM 은 후보를 제시할 뿐, `confirmed=1` 은 사람만 만든다(환각 매핑이 곧
   데이터 오염이므로). M1 의 "기준정보만 마스터" 원칙과 동일 계열의 안전장치.
2. **M2 는 메타데이터만 저장.** 실제 트랜잭션/대량 데이터는 저장 금지(M3 온디맨드). external_schemas 에
   담는 건 "필드가 존재한다"는 사실이지 그 값이 아니다.
3. **온톨로지 재사용.** 외부 스키마 필드는 가능하면 M1 `entity_types` 의 오브젝트 타입에 정렬한다
   (시스템을 새로 만들지 않는다 — G2/M1 과 공용).
4. **비신뢰 입력 취급.** 외부 스키마 텍스트·필드명은 프롬프트 인젝션 방어 대상(자료로만, 지시 금지).

## 2. 데이터 모델 — `data/master/master.db` 확장

M1 이 예약 생성한 두 테이블을 사용하고, 스키마 등록용 한 테이블을 추가한다.

```sql
-- (M1 예약, 그대로 사용) 연계 시스템 등록부
-- external_systems(system_id, name, mcp_endpoint, auth_ref, scope, status, created_at)

-- (신규) 외부 시스템의 스키마 — 엔티티(테이블)와 필드 목록. 값이 아니라 '구조'만 저장.
CREATE TABLE IF NOT EXISTS external_schemas (
    system_id   TEXT NOT NULL,
    entity      TEXT NOT NULL,           -- 외부 테이블/오브젝트명 (예: 'MARA', 'work_order')
    field       TEXT NOT NULL,           -- 외부 필드명 (예: 'MATNR')
    field_type  TEXT DEFAULT '',         -- string|number|date 등(외부 신고값, 신뢰X)
    is_key      INTEGER DEFAULT 0,       -- 외부 기본키 여부(크로스워크 후보 힌트)
    mapped_type TEXT DEFAULT '',         -- 정렬된 M1 entity_types.type_id (선택)
    note        TEXT DEFAULT '',
    source      TEXT DEFAULT 'user',     -- user | csv_import | llm_introspect
    PRIMARY KEY (system_id, entity, field)
);
CREATE INDEX IF NOT EXISTS idx_extschema_sys ON external_schemas(system_id, entity);

-- (M1 예약, 확장) 마스터 코드 ↔ 외부 키 크로스워크
-- key_crosswalk(master_code, system_id, external_key, confirmed)
--   ↑ M1 스키마 유지. external_key 는 external_schemas 의 (entity.field=value) 를 가리키는 논리 키.
--   confirmed: 0=LLM/휴리스틱 제안, 1=사람 승인(사용 가능). 제안 근거·점수는 아래 별도 테이블.
CREATE TABLE IF NOT EXISTS crosswalk_proposals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    master_code TEXT NOT NULL,
    system_id   TEXT NOT NULL,
    external_key TEXT NOT NULL,          -- 제안된 외부 키 (entity.field 또는 값)
    confidence  REAL DEFAULT 0.0,        -- 제안 신뢰도(0~1)
    rationale   TEXT DEFAULT '',         -- LLM/휴리스틱 제안 근거
    status      TEXT DEFAULT 'pending',  -- pending | approved | rejected
    created_at  TEXT NOT NULL
);
```

**설계 노트**: 승인된 매핑(`key_crosswalk.confirmed=1`)과 제안(`crosswalk_proposals`)을 분리한다.
제안은 여러 후보가 경쟁할 수 있고 기각 이력을 남겨야 하며, 승인은 유일·확정이기 때문이다.

## 3. 크로스워크 매핑 워크플로우 (LLM 초안 + 사람 승인)

```
[1] 시스템 등록      → external_systems INSERT (status=inactive)
[2] 스키마 수집      → external_schemas INSERT (CSV 업로드 또는 수기; 후일 M3 introspect)
[3] 매핑 초안 생성   → (Flash 1콜, 온톨로지 스키마 제약) master_records/aliases ↔ external_schemas
                        유사도·별칭·타입 정렬로 후보 산출 → crosswalk_proposals (status=pending)
[4] 사람 검토·승인   → 승인: key_crosswalk UPSERT(confirmed=1) + proposal.status=approved
                        기각: proposal.status=rejected (이력 보존)
[5] 활성화           → external_systems.status=active (승인 매핑 ≥1건일 때만)
```

- **[3] 초안 생성의 결정론 뼈대 + LLM 보강**: 1차로 **별칭/이름 정확·부분 일치(LLM 0콜)** 로 후보를
  뽑고(M1 별칭 감지 재사용), 애매한 것만 Flash 로 판정(온톨로지 entity_types 제약 JSON 강제, 자유생성
  금지). → 쿼터 절약 + 환각 억제.
- **[4] 승인 게이트**는 지식허브 3단계·스킬 진화 패널과 동일 UX 패턴(제안 목록 → 승인/기각).

## 4. API 명세 — `api/routes/crosswalk_control.py`, prefix `/api/v1/crosswalk`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/systems` | 연계 시스템 목록 |
| POST | `/systems` | 시스템 등록 `{system_id, name, mcp_endpoint?, scope?}` (중복 409) |
| PUT | `/systems/{system_id}` | 수정(상태 등) |
| DELETE | `/systems/{system_id}` | 제거(매핑 존재 시 409 또는 소프트) |
| GET | `/systems/{system_id}/schema` | 외부 스키마(엔티티/필드) 조회 |
| POST | `/systems/{system_id}/schema/import` | CSV: `entity,field,field_type,is_key` 일괄 등록 |
| POST | `/systems/{system_id}/propose` | 매핑 초안 생성(결정론+Flash) → proposals 반환 |
| GET | `/systems/{system_id}/proposals` | 제안 목록(pending/approved/rejected) |
| POST | `/proposals/{id}/approve` | 승인 → key_crosswalk confirmed=1 |
| POST | `/proposals/{id}/reject` | 기각(이력 보존) |
| GET | `/systems/{system_id}/mappings` | 승인된 크로스워크(confirmed=1) 조회 |

응답 봉투/에러코드/`_safe_id` 는 M1(master_control) 관례 준수. propose 만 LLM(Flash) 사용, 나머지 0콜.

## 5. UI 개요 — 기준정보 마스터 패널 내 "🔗 연계/크로스워크" 탭

M1 `MasterDataPanel` 에 탭 추가(또는 별도 패널):
- 시스템 목록/등록(좌) + 선택 시스템의 스키마 테이블·CSV 업로드(우)
- [매핑 초안 생성] 버튼 → 제안 목록(신뢰도·근거 표시) → 각 행 [승인]/[기각]
- 승인된 크로스워크 뷰(내부 master_code ↔ 외부 key), 활성화 토글

## 6. 검증 규칙·구현 체크리스트

**검증**: `system_id ^[a-z0-9_-]{2,32}$` / external entity·field 는 128자 제한·제어문자 금지 /
confidence 0~1 / 승인은 confirmed=1 유일(동일 master_code+system_id 재승인 시 교체).

**구현 순서**(예상: 백엔드 중, UI 소):
1. `core/master_data.py` 에 external_schemas·crosswalk_proposals DDL 추가 + CRUD·propose·approve/reject
   (M1 모듈 확장 — 별칭 감지·캐시 무효화 재사용). 또는 `core/crosswalk.py` 분리(응집도 판단).
2. `api/routes/crosswalk_control.py` + main.py 등록
3. propose 초안기: 결정론(별칭/이름 일치) 1차 + Flash 판정(온톨로지 제약) 2차
4. UI 탭
5. 테스트: 시스템/스키마 CRUD → propose → approve/reject → mappings, 승인 전 미사용 보장

**M3 연결점(이 설계가 준비하는 것)**: `external_systems.mcp_endpoint`·`auth_ref`, 승인된 크로스워크가
곧 M3 의 "가상 통합 주소록". M3 는 여기에 as-of 타임스탬프·TTL 캐시·읽기전용 온디맨드 조회를 더한다.

## 7. 열린 질문(검토 시 결정)
- (a) M2 로직을 `master_data.py` 확장 vs `crosswalk.py` 분리 — 파일 크기·응집도로 판단.
- (b) propose 의 Flash 사용을 옵트인 토글로 둘지(완주 우선·쿼터 절약 기조).
- (c) external_key 표현: `entity.field` 수준 매핑 vs 특정 값(row) 매핑 — M3 조회 단위와 함께 확정.
