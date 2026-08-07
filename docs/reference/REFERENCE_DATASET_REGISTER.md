# Reference Dataset Recovery Register

> 원본 진실원본: `docs/reference/`  
> 기계 판독 등록부: `data/reference_registry.json`  
> 갱신 도구: `scripts/build_reference_inventory.py` 또는 `POST /api/v1/reference/scan`

## 현재 등록 상태

- 원본 자산: **68건**
- 본문 추출 가능: **67건** (PDF 11, DOCX 5, PPTX 50, TXT 1)
- 변환 필요: **1건** (`전사교육자료/2026/2026 자사교육_11 생산통합_전련_250521.ppt`)
- 등록부 승인 절차를 통한 신규 지식팩 색인: **0건**
- 검토·승인 대기: **68건**

기존 `core-m3-standards`에는 최상위 PDF 10개가 선행 등록되어 있다. 이 등록부는 그와 별개로 원본 전체의 SHA-256, 상대 경로, 형식, 추천 지식팩, 조직 범위, 분류, 추출 가능 여부와 승인 상태를 보존한다. 원본이 있다고 해서 자동으로 모든 에이전트 프롬프트나 MDM에 넣지 않는다.

## 추천 지식팩 배치

| 지식팩 | 자산 수 | 기본 범위 |
|---|---:|---|
| `manufacturing-standards` | 7 | LS MnM 공통 |
| `battery-materials-operations` | 6 | 배터리소재 사업부 |
| `copper-smelting-operations` | 16 | 동제련 사업부 |
| `corporate-management-finance` | 11 | LS MnM 공통 |
| `scm-procurement-logistics` | 8 | LS MnM 공통 |
| `quality-esg-safety` | 8 | LS MnM 공통 |
| `innovation-rnd-people` | 12 | LS MnM 공통 |

## 승인·색인 절차

1. 데이터 오너가 등록부의 조직 범위·분류·추천 지식팩을 검토한다.
2. `approval_status`를 승인으로 전환한다.
3. 승인된 문서만 해당 지식팩에 본문 추출·청킹·색인한다.
4. 프로젝트에는 기업·사업부·업무 문맥에 맞는 팩만 연결한다.
5. 문서의 용어·필드·산식·수치는 별도 검토 후 각각 용어사전·카탈로그·데이터 계약·MDM으로 승격한다.

구형 `.ppt`는 신뢰 가능한 본문 추출을 하지 않는다. 원본은 유지하고 PPTX 또는 PDF로 변환한 뒤 등록한다.
