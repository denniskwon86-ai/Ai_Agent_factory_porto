## 1. 오늘 Task에 대한 아키텍처 개요

본 Task는 "전체 공통 아키텍처 수립"으로, 프로젝트 전반의 기술적 기반을 다지는 데 중점을 둡니다. WBS Task의 'scope'에 명시된 기능들을 중심으로, 핵심 엔티티를 포함하는 데이터베이스 스키마, 주요 모듈 간 통신을 위한 RESTful API 엔드포인트 및 데이터 형식, 그리고 소스 코드 관리를 위한 표준 디렉토리 구조를 정의합니다.

**주요 설계 범위:**

*   **데이터베이스 스키마:** `Companies`, `Users`, `Products`, `Materials`, `BOM`, `Suppliers`, `DemandForecasts` 엔티티를 중심으로 핵심 필드와 관계를 정의합니다. (이전 출력에서 이미 상세하게 정의되었으므로, 본 Task에서는 이 스키마를 기반으로 합니다.)
*   **API 엔드포인트:** 마스터 데이터 관리(제품, 자재, BOM, 공급업체) 및 수요 예측 데이터 관리를 위한 RESTful API 엔드포인트를 정의합니다. 사용자 인증/등록 관련 API는 "사용자 로그인 기능은 생략하고 우선 라이트하게 구현"하라는 피드백을 반영하여, 사용자 정보 조회 및 수정/삭제에 집중합니다.
*   **데이터 흐름:** Frontend, API Gateway, 각 Backend Service (Master Data, Planning), Database 간의 데이터 흐름을 설명합니다.
*   **디렉토리 구조:** Backend 및 Frontend 프로젝트의 표준 디렉토리 구조를 제시합니다.
*   **공통 라이브러리/유틸리티:** 프로젝트 전반에 걸쳐 유용할 수 있는 공통 라이브러리 및 유틸리티 함수를 제안합니다.
*   **개발/배포 전략:** Docker 기반의 개발 환경 및 CI/CD를 활용한 배포 전략 개요를 수립합니다.

**피드백 반영:** "사용자 로그인 기능은 생략하고 우선 라이트하게 구현"하라는 지시에 따라, `POST /auth/login` 및 `POST /auth/register` 엔드포인트는 제외하고, 사용자 정보 조회, 수정, 삭제에 대한 API만 남겨둡니다.

## 2. 오늘 Task에 필요한 데이터베이스 스키마 (ERD 개념)

이전 출력에서 상세하게 정의된 데이터베이스 스키마를 그대로 활용합니다. 본 Task의 범위 내에서 추가적인 변경이나 확장은 없습니다.

**핵심 엔티티 및 관계:**

*   **`Companies` (기업 정보):**
    *   `company_id` (PK, UUID)
    *   `company_name` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`Users` (사용자 정보):**
    *   `user_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `username` (VARCHAR, UNIQUE)
    *   `email` (VARCHAR, UNIQUE)
    *   `password_hash` (VARCHAR) - **로그인 기능 제외로 인해 실제 저장되지 않거나, 최소한의 정보만 저장될 수 있습니다.**
    *   `role` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`Products` (제품 정보):**
    *   `product_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `product_code` (VARCHAR)
    *   `product_name` (VARCHAR)
    *   `unit_of_measure` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`Materials` (원자재 정보):**
    *   `material_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `material_code` (VARCHAR)
    *   `material_name` (VARCHAR)
    *   `unit_of_measure` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`BOM` (BOM 정보 - Bill of Materials):**
    *   `bom_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `parent_product_id` (FK, UUID)
    *   `child_material_id` (FK, UUID)
    *   `quantity_per_parent` (DECIMAL)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`Suppliers` (공급업체 정보):**
    *   `supplier_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `supplier_name` (VARCHAR)
    *   `contact_person` (VARCHAR)
    *   `phone` (VARCHAR)
    *   `email` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

*   **`DemandForecasts` (수요 예측 정보):**
    *   `forecast_id` (PK, UUID)
    *   `company_id` (FK, UUID)
    *   `product_id` (FK, UUID)
    *   `forecast_date` (DATE)
    *   `forecast_quantity` (DECIMAL)
    *   `forecast_type` (VARCHAR)
    *   `created_at` (TIMESTAMP)
    *   `updated_at` (TIMESTAMP)

**관계 (Relationships):**

*   `Companies` 1 : N `Users`
*   `Companies` 1 : N `Products`
*   `Companies` 1 : N `Materials`
*   `Companies` 1 : N `BOM`
*   `Companies` 1 : N `Suppliers`
*   `Companies` 1 : N `DemandForecasts`
*   `Products` 1 : N `BOM` (as parent)
*   `Materials` 1 : N `BOM` (as child)

## 3. 시스템 컴포넌트 간 데이터 흐름도 설명

본 Task에서 정의된 공통 아키텍처를 기반으로, 주요 컴포넌트 간의 데이터 흐름을 RESTful API를 통해 설명합니다. 사용자 로그인 기능은 제외되었으므로, 인증 관련 흐름은 간소화됩니다.

**주요 컴포넌트:**

*   **Frontend (Client Application):** 사용자 인터페이스를 제공하고 사용자의 요청을 Backend API로 전달합니다.
*   **Backend API Gateway:** 모든 외부 요청을 받아 적절한 서비스로 라우팅하는 단일 진입점 역할을 합니다.
*   **User Service:** 사용자 정보 조회, 수정, 삭제 등 사용자 관련 비즈니스 로직을 처리합니다. (로그인/등록 제외)
*   **Master Data Service:** 제품, 자재, BOM, 공급업체 등 마스터 데이터 관리를 담당합니다.
*   **Planning Service:** 수요 예측 데이터 관리를 담당합니다.
*   **Database:** 모든 영구 데이터를 저장합니다.

**데이터 흐름 예시:**

1.  **사용자 정보 조회 (특정 사용자):**
    *   **Frontend** -> `GET /api/v1/users/{userId}?companyId={companyId}` (Authorization: Bearer {JWT_TOKEN}) -> **API Gateway**
    *   **API Gateway** -> `GET /users/{userId}?companyId={companyId}` -> **User Service**
    *   **User Service** -> `SELECT * FROM Users WHERE user_id = ? AND company_id = ?` -> **Database**
    *   **Database** -> User 정보 반환
    *   **User Service** -> **API Gateway** -> **Frontend** (User 정보 JSON)

2.  **제품 목록 조회:**
    *   **Frontend** -> `GET /api/v1/products?companyId={companyId}` (Authorization: Bearer {JWT_TOKEN}) -> **API Gateway**
    *   **API Gateway** -> `GET /master-data/products?companyId={companyId}` -> **Master Data Service**
    *   **Master Data Service** -> `SELECT * FROM Products WHERE company_id = ?` -> **Database**
    *   **Database** -> 제품 목록 반환
    *   **Master Data Service** -> **API Gateway** -> **Frontend** (제품 목록 JSON)

3.  **수요 예측 데이터 생성:**
    *   **Frontend** -> `POST /api/v1/demand-forecasts` (Authorization: Bearer {JWT_TOKEN}) -> **API Gateway**
        *   Request Body: `{ "companyId": "...", "productId": "...", "forecastDate": "...", "forecastQuantity": ..., "forecastType": "..." }`
    *   **API Gateway** -> `POST /planning/demand-forecasts` -> **Planning Service**
    *   **Planning Service** -> `INSERT INTO DemandForecasts (company_id, product_id, forecast_date, forecast_quantity, forecast_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, NOW(), NOW())` -> **Database**
    *   **Database** -> 성공/실패 결과 반환
    *   **Planning Service** -> **API Gateway** -> **Frontend** (성공 메시지 또는 오류 정보)

**API 엔드포인트 및 데이터 형식 (RESTful):**

*   **Base URL:** `/api/v1`
*   **Authentication:** JWT (JSON Web Token) 기반 인증. 모든 요청 헤더에 `Authorization: Bearer {JWT_TOKEN}` 포함. (로그인/등록 제외)
*   **Data Format:** JSON

**주요 엔드포인트 예시:**

*   **Users:** (로그인/등록 제외)
    *   `GET /users/{userId}`: 특정 사용자 정보 조회 (companyId 필터링 포함)
        *   Query Params: `companyId` (필수)
    *   `PUT /users/{userId}`: 특정 사용자 정보 수정 (companyId 필터링 포함)
        *   Request Body: `{ "email": "...", "role": "..." }` (수정 가능한 필드)
    *   `DELETE /users/{userId}`: 특정 사용자 삭제 (companyId 필터링 포함)

*   **Master Data (Products, Materials, BOM, Suppliers):**
    *   `GET /{resource_type}`: 특정 기업의 모든 리소스 조회 (e.g., `GET /products?companyId=...`)
        *   Query Params: `companyId` (필수)
    *   `POST /{resource_type}`: 새 리소스 생성 (e.g., `POST /products`)
        *   Request Body: `{ "companyId": "...", "productCode": "...", "productName": "...", "unitOfMeasure": "..." }` (리소스 타입별 필드)
    *   `GET /{resource_type}/{resourceId}`: 특정 리소스 조회 (e.g., `GET /products/abc-123`)
        *   Query Params: `companyId` (필수)
    *   `PUT /{resource_type}/{resourceId}`: 특정 리소스 수정 (e.g., `PUT /products/abc-123`)
        *   Request Body: (리소스 타입별 수정 가능한 필드)
        *   Query Params: `companyId` (필수)
    *   `DELETE /{resource_type}/{resourceId}`: 특정 리소스 삭제 (e.g., `DELETE /products/abc-123`)
        *   Query Params: `companyId` (필수)

*   **Planning (Demand Forecasts):**
    *   `GET /demand-forecasts`: 수요 예측 조회 (필터링 가능)
        *   Query Params: `companyId` (필수), `productId`, `dateFrom`, `dateTo`, `forecastType`
    *   `POST /demand-forecasts`: 수요 예측 생성
        *   Request Body: `{ "companyId": "...", "productId": "...", "forecastDate": "...", "forecastQuantity": ..., "forecastType": "..." }`
    *   `PUT /demand-forecasts/{forecastId}`: 수요 예측 수정
        *   Request Body: (수정 가능한 필드)
    *   `DELETE /demand-forecasts/{forecastId}`: 수요 예측 삭제

**디렉토리 구조 정의:**

```
/project-root
├── /backend
│   ├── /src
│   │   ├── /api                 # API 엔드포인트 정의 (controllers)
│   │   ├── /config              # 애플리케이션 설정
│   │   ├── /database            # DB 연결 및 ORM 설정
│   │   ├── /models              # 데이터베이스 모델 정의
│   │   ├── /services            # 비즈니스 로직 구현 (User, MasterData, Planning 등)
│   │   ├── /utils               # 공통 유틸리티 함수
│   │   └── /middleware          # 요청 처리 미들웨어 (인증 등)
│   ├── /tests                 # 백엔드 테스트 코드
│   ├── Dockerfile
│   ├── package.json
│   └── README.md
├── /frontend
│   ├── /public                # 정적 파일 (index.html, favicon 등)
│   ├── /src
│   │   ├── /assets            # 이미지, 폰트 등
│   │   ├── /components        # 재사용 가능한 UI 컴포넌트
│   │   ├── /pages             # 페이지별 컴포넌트
│   │   ├── /services          # API 호출 서비스
│   │   ├── /store             # 상태 관리 (e.g., Redux, Vuex)
│   │   ├── /utils             # 프론트엔드 유틸리티 함수
│   │   └── App.js             # 메인 애플리케이션 컴포넌트
│   ├── /tests                 # 프론트엔드 테스트 코드
│   ├── package.json
│   └── README.md
├── /docs                    # 프로젝트 문서
├── .gitignore
├── README.md
└── docker-compose.yml       # 개발 환경용 Docker Compose
```

**공통 라이브러리 및 유틸리티 함수:**

*   **Backend:**
    *   `utils/crypto.js`: 비밀번호 해싱 및 검증 함수 (로그인 기능 제외로 인해 사용되지 않음)
    *   `utils/jwt.js`: JWT 생성 및 검증 함수 (인증 미들웨어에서 사용)
    *   `utils/responseHandler.js`: 일관된 API 응답 형식 처리
    *   `utils/logger.js`: 로깅 유틸리티
    *   `utils/uuidGenerator.js`: UUID 생성 유틸리티
*   **Frontend:**
    *   `utils/apiClient.js`: Axios 등을 이용한 API 호출 래퍼 (인증 헤더 자동 추가)
    *   `utils/formatters.js`: 날짜, 숫자 포맷팅 함수
    *   `utils/validators.js`: 입력값 검증 함수

**개발 환경 및 배포 전략 개요:**

*   **개발 환경:**
    *   Docker를 활용하여 개발, 스테이징, 프로덕션 환경의 일관성 유지.
    *   `docker-compose.yml`을 통해 DB, 백엔드, 프론트엔드 컨테이너 구성.
    *   각 개발자는 로컬 환경에서 Docker Compose 실행.
*   **배포 전략:**
    *   CI/CD 파이프라인 구축 (e.g., GitHub Actions, GitLab CI).
    *   코드 푸시 시 자동 빌드, 테스트, 배포 프로세스 정의.
    *   배포 대상: 클라우드 플랫폼 (AWS, GCP, Azure 등) 또는 자체 서버.
    *   초기에는 수동 배포로 시작하여 점진적으로 자동화.