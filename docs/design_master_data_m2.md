# M2 상세 설계 — 스키마 레지스트리 + 키 크로스워크 (Schema Registry & Key Crosswalk)

> **ECM 연계 확장(2026-07-28):** 크로스워크는 법인·사업부·사업장별 로컬 키와 전사 표준 키의 범위를 함께 기록해야 하며, 가상/경쟁사 문맥의 키가 실제 운영계 키 또는 연결 자격증명으로 해석되지 않게 한다. 상세 기준: [`design_enterprise_context_master.md`](design_enterprise_context_master.md).

> 작성: 2026-07-22 | 상태: **설계 확정(구현 대기 — 열린 질문 a/b/c 승인 완료)** | 선행: M1(`docs/design_master_data_m1.md`, 구현 완료)
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
-- [역할] '조인 컬럼 정의' 계층: 외부 필드가 우리 어느 타입/속성에 대응하는지(변환 규칙).
CREATE TABLE IF NOT EXISTS external_schemas (
    system_id   TEXT NOT NULL,
    entity      TEXT NOT NULL,           -- 외부 테이블/오브젝트명 (예: 'MARA', 'work_order')
    field       TEXT NOT NULL,           -- 외부 필드명 (예: 'MATNR', 'LEAD_TIME_HRS')
    field_type  TEXT DEFAULT '',         -- string|number|date 등(외부 신고값, 신뢰X)
    is_key      INTEGER DEFAULT 0,       -- 외부 기본키 여부(크로스워크 후보 힌트)
    mapped_type TEXT DEFAULT '',         -- 정렬된 M1 entity_types.type_id (엔티티 정렬, 선택)
    mapped_attr TEXT DEFAULT '',         -- [(c) 확정] 이 외부 필드가 대응하는 M1 속성명(조인 컬럼)
                                         --   예: LEAD_TIME_HRS → '표준리드타임_h'. 비면 미매핑.
    note        TEXT DEFAULT '',
    source      TEXT DEFAULT 'user',     -- user | csv_import | llm_introspect
    PRIMARY KEY (system_id, entity, field)
);
CREATE INDEX IF NOT EXISTS idx_extschema_sys ON external_schemas(system_id, entity);

-- (M1 예약, 확장) 마스터 코드 ↔ 외부 키 크로스워크
-- key_crosswalk(master_code, system_id, external_key, confirmed)
--   ↑ M1 스키마 유지(컬럼 추가 없음). [역할] '값 번역표(브리지)' 계층: 우리 골든 레코드 1건이
--     외부 시스템에선 어느 인스턴스 키인지. 두 시스템의 키 값 공간이 다르므로 반드시 필요.
--   [(c) 확정] external_key 형식 = "<entity>:<pk_field>=<value>"
--     예: 'PROC-ASSY-01' → system='mes', external_key='work_order:WO_TYPE=ASSY'
--         'MAT-100' → system='sap', external_key='MARA:MATNR=100-200-30'
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
1. **[(a) 확정] DDL 은 `master_data.py` 가 소유** — `external_schemas`·`crosswalk_proposals` 를
   `master_data._DDL` 에 추가(스키마 초기화 단일화, `master.db` 는 한 파일). 저수준 `_connect`·별칭 감지
   `_alias_hit` 도 master_data 소유.
2. **[(a) 확정] 비즈니스 로직은 `core/crosswalk.py` 분리** — systems/schemas CRUD·propose·approve/reject.
   master_data 의 `_connect`/`_alias_hit` 를 import 재사용(중복 구현 금지). LLM(propose)이 들어가는
   M2 를 LLM 0콜인 M1 과 파일로 격리.
3. `api/routes/crosswalk_control.py` + main.py 등록
4. propose 초안기: 결정론(별칭/이름 일치, LLM 0콜) 1차 + **[(b) 확정] Flash 판정은 옵트인 토글**
   (온톨로지 entity_types 제약 JSON 강제; 기본 off, 완주·쿼터 절약 기조). 애매한 후보만 Flash.
5. UI 탭(기준정보 마스터 패널 내 "🔗 연계/크로스워크")
6. 테스트: 시스템/스키마 CRUD → propose → approve/reject → mappings, 승인 전 미사용 보장.
   `external_key` 형식·`mapped_attr` 대응 검증 포함.

**M3 연결점(이 설계가 준비하는 것)**: `external_systems.mcp_endpoint`·`auth_ref`, 승인된 크로스워크가
곧 M3 의 "가상 통합 주소록". M3 는 여기에 as-of 타임스탬프·TTL 캐시·읽기전용 온디맨드 조회를 더한다.

## 7. 확정된 결정 (2026-07-22 사용자 승인)
- **(a) ✅ `core/crosswalk.py` 분리 + DDL 은 `master_data.py` 소유.** 파일 크기(master_data 552줄)·
  관심사(내부 골든 vs 외부 매핑)·LLM 유무(M1 0콜 / M2 Flash) 분리. 단 `master.db`·`_connect`·별칭
  감지는 공유(§6-1·2).
- **(b) ✅ propose 의 Flash 판정은 옵트인 토글.** 기본은 결정론(별칭/이름 일치, LLM 0콜)만. 애매한
  후보에 한해 사용자가 Flash 를 켤 때만 호출(완주·쿼터 절약 기조).
- **(c) ✅ 2계층 매핑.** `key_crosswalk` = 값 번역표(브리지, 인스턴스 수준, `external_key="entity:field=value"`),
  `external_schemas.mapped_attr` = 조인 컬럼 정의(필드↔속성). RDB 로 치면 "조인 컬럼 선정 + 값 번역
  테이블" 이 둘 다 필요한 구조(이종 시스템이라 키 값 공간이 달라서). 실제 값 조회는 M3.

착수 준비 완료 — 위 결정 반영본으로 M2 구현 가능.
