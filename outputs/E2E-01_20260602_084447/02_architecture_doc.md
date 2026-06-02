## 시스템 아키텍처 및 DB 설계 (WBS Task: E2E-01) - 라이트 버전

### 1. 오늘 Task에 대한 아키텍처 개요

본 WBS Task는 "전체 공통 아키텍처 수립"을 목표로 하며, 프로젝트 전반의 기술 기반이 될 핵심 요소들을 **라이트하게** 정의합니다. 구체적으로는 프로젝트 전반에 사용될 **핵심 데이터베이스 스키마**, 주요 모듈 간 통신을 위한 **API 엔드포인트 및 데이터 형식 정의 (RESTful)**, 그리고 **소스 코드 및 관련 파일 관리를 위한 표준 디렉토리 구조**를 정의합니다. 이는 향후 개별 기능 개발 시 일관성을 유지하고, 모듈 간의 효율적인 연동을 지원하는 데 기여할 것입니다.

### 2. 오늘 Task에 필요한 데이터베이스 스키마 (ERD 개념)

WBS Task의 'scope'에 명시된 "프로젝트 전반에 사용될 데이터베이스 스키마 설계 (핵심 엔티티 중심)"에 따라, 배터리 소재 제조 공장 S&OP 시뮬레이터의 **핵심적인 데이터 모델**을 라이트하게 정의합니다.

**핵심 엔티티:**

*   **Product (제품 정보):**
    *   `product_id` (PK, UUID): 제품 고유 식별자
    *   `name` (VARCHAR): 제품명
    *   `unit_of_measure` (VARCHAR): 측정 단위 (예: kg, ton)

*   **Material (원자재 정보):**
    *   `material_id` (PK, UUID): 원자재 고유 식별자
    *   `name` (VARCHAR): 원자재명
    *   `unit_of_measure` (VARCHAR): 측정 단위 (예: kg, ton)

*   **BOM (Bill of Materials - 자재 명세서):**
    *   `bom_id` (PK, UUID): BOM 고유 식별자
    *   `parent_product_id` (FK, UUID): 상위 제품 ID
    *   `child_material_id` (FK, UUID): 하위 자재 ID
    *   `quantity` (DECIMAL): 상위 제품 1단위 생산에 필요한 하위 자재의 수량

*   **Demand (수요 정보):**
    *   `demand_id` (PK, UUID): 수요 고유 식별자
    *   `product_id` (FK, UUID): 대상 제품 ID
    *   `period` (DATE): 수요 발생 시점 (일, 주, 월 등)
    *   `quantity` (DECIMAL): 수요량

*   **Inventory (재고 정보):**
    *   `inventory_id` (PK, UUID): 재고 고유 식별자
    *   `product_id` (FK, UUID, NULLABLE): 제품 재고 ID
    *   `material_id` (FK, UUID, NULLABLE): 원자재 재고 ID
    *   `quantity` (DECIMAL): 현재 재고량
    *   `as_of_date` (DATE): 재고 기준일

*   **ProductionPlan (생산 계획 정보):**
    *   `plan_id` (PK, UUID): 생산 계획 고유 식별자
    *   `product_id` (FK, UUID): 생산할 제품 ID
    *   `period` (DATE): 생산 계획 기간 (예: 주차, 월)
    *   `planned_quantity` (DECIMAL): 계획 생산량

**관계 (Relationship):**

*   `Product` 1 : N `BOM` (as parent)
*   `Material` 1 : N `BOM` (as child)
*   `Product` 1 : N `Demand`
*   `Product` 1 : N `Inventory` (if product inventory)
*   `Material` 1 : N `Inventory` (if material inventory)
*   `Product` 1 : N `ProductionPlan`

### 3. 시스템 컴포넌트 간 데이터 흐름도 설명

본 WBS Task는 시스템의 전체적인 구조와 API 규격을 정의하므로, **주요 모듈 간의 API 호출 및 데이터 교환 방식**에 초점을 맞춥니다.

**가정:**

*   **Frontend (Client):** 사용자 인터페이스 (Web Application)
*   **Backend API Gateway:** 모든 클라이언트 요청을 받아 적절한 서비스로 라우팅하는 단일 진입점.
*   **Core Service:** 핵심 비즈니스 로직 (생산 계획, 재고 관리, MRP 계산 등)을 담당하는 서비스.

**데이터 흐름 설명:**

1.  **사용자 요청 (Frontend -> API Gateway):**
    *   사용자가 Frontend에서 작업을 수행합니다 (예: 제품 목록 조회).
    *   Frontend는 HTTP 요청 (GET, POST 등)을 통해 API Gateway로 데이터를 전송합니다.
    *   **API 엔드포인트 예시:**
        *   `GET /api/v1/products`: 모든 제품 목록 조회
        *   `POST /api/v1/production-plans`: 새로운 생산 계획 생성

2.  **요청 라우팅 및 처리 (API Gateway -> Core Service):**
    *   API Gateway는 요청을 Core Service의 해당 API 엔드포인트로 전달합니다.

3.  **비즈니스 로직 수행 및 데이터베이스 연동 (Core Service):**
    *   Core Service는 요청을 처리하고, 필요시 데이터베이스에 접근합니다.
    *   **데이터 형식 (JSON 예시):**
        *   **생산 계획 생성 요청 (POST /api/v1/production-plans):**
            ```json
            {
              "product_id": "uuid-product-123",
              "period": "2024-07-22",
              "planned_quantity": 1000
            }
            ```
        *   **제품 목록 조회 응답 (GET /api/v1/products):**
            ```json
            [
              {
                "product_id": "uuid-product-123",
                "name": "NCM 양극재",
                "unit_of_measure": "kg"
              }
            ]
            ```

4.  **응답 반환 (Core Service -> API Gateway -> Frontend):**
    *   Core Service는 처리 결과를 API Gateway를 통해 Frontend에 반환합니다.

**API 엔드포인트 및 데이터 형식 정의 (RESTful):**

*   **자원 중심 설계:** `products`, `demands`, `production-plans` 등.
*   **HTTP 메소드 활용:** `GET`, `POST`.
*   **버전 관리:** `/api/v1/`.
*   **JSON 형식:** 요청 및 응답 본문.

**소스 코드 및 관련 파일 관리 (디렉토리 구조):**

*   **`src/`**: 소스 코드 루트 디렉토리
    *   **`api/`**: API 관련 코드
        *   `v1/`
            *   `products.routes.ts`
            *   `production-plans.controller.ts`
    *   **`services/`**: 비즈니스 로직 서비스
        *   `product.service.ts`
        *   `production-plan.service.ts`
    *   **`utils/`**: 공통 유틸리티 함수 (필요시)