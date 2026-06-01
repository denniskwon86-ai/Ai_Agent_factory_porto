# 1. 전체 아키텍처 개요

본 시스템은 프로젝트 전반에 걸쳐 적용될 기술 표준 및 핵심 데이터 구조를 정의하고, 특히 자재, 생산, 재고, 주문과 같은 핵심 비즈니스 도메인을 지원하는 견고한 기반을 마련하는 것을 목표로 합니다. 확장성과 유지보수 용이성을 최우선으로 고려하여 마이크로서비스 아키텍처(MSA) 기반으로 설계됩니다.

**주요 구성 요소:**

*   **API Gateway:** 모든 외부 요청의 단일 진입점 역할을 합니다. 요청 라우팅, 인증/인가, 로깅, 속도 제한 등의 기능을 수행하여 내부 서비스의 복잡성을 외부에 노출하지 않습니다.
*   **Service Discovery & Configuration Server:** 마이크로서비스 환경에서 서비스 인스턴스를 동적으로 등록하고 찾을 수 있도록 하며, 모든 서비스의 중앙 집중식 설정 관리를 제공합니다.
*   **Identity & Access Management (IAM) Service:** 사용자 인증 및 권한 부여를 담당하여 시스템 전반의 보안을 강화합니다. (향후 확장 시 고려)
*   **Material Service (자재 서비스):** 자재 마스터 데이터, BOM(Bill of Materials) 등 자재 관련 핵심 정보를 관리합니다.
*   **Production Service (생산 서비스):** 생산 오더, 작업 지시, 생산 스케줄링 등 생산 계획 및 실행 관련 비즈니스 로직을 처리합니다.
*   **Inventory Service (재고 서비스):** 재고 수준, 입출고, 창고 위치 관리 등 재고 관련 비즈니스 로직을 담당합니다.
*   **Order Service (주문 서비스):** 고객 주문(판매 주문), 구매 주문 등 주문 생성, 조회, 상태 관리 비즈니스 로직을 처리합니다.
*   **Message Broker (Apache Kafka/RabbitMQ):** 서비스 간 비동기 통신을 위한 핵심 인프라입니다. 이벤트 기반 아키텍처를 지원하여 서비스 간의 결합도를 낮추고 시스템의 탄력성과 확장성을 높입니다.
*   **Database:** 각 마이크로서비스는 독립적인 데이터베이스를 가질 수 있으며, 핵심 비즈니스 데이터는 관계형 데이터베이스를 사용합니다.
*   **Centralized Logging & Monitoring:** 시스템 전반의 로그를 수집하고 실시간으로 모니터링하여 문제 발생 시 신속하게 감지하고 해결할 수 있도록 합니다.
*   **Containerization & Orchestration:** Docker를 이용한 서비스 컨테이너화 및 Kubernetes를 이용한 컨테이너 오케스트레이션을 통해 배포 및 운영의 효율성을 극대화합니다.

**확장성 고려 사항:**

*   **마이크로서비스 아키텍처:** 각 도메인 서비스(자재, 생산, 재고, 주문 등)는 독립적으로 개발, 배포 및 확장이 가능하도록 설계하여 특정 서비스의 부하 증가 시 해당 서비스만 유연하게 스케일링할 수 있습니다.
*   **비동기 처리:** Message Broker를 활용하여 서비스 간의 직접적인 의존성을 줄이고, 대규모 트랜잭션이나 시간이 오래 걸리는 작업을 비동기적으로 처리하여 시스템 응답성을 향상시킵니다.
*   **Polyglot Persistence:** 각 서비스의 특성에 맞는 최적의 데이터베이스를 선택하여 데이터 처리 성능을 최적화할 수 있습니다.
*   **클라우드 네이티브 설계:** Kubernetes와 같은 컨테이너 오케스트레이션 도구를 활용하여 클라우드 환경에서의 자동 확장 및 고가용성을 지원합니다.

**유지보수 용이성 고려 사항:**

*   **모듈화된 설계:** 각 마이크로서비스는 명확한 책임과 경계를 가지도록 설계하여 코드의 이해와 수정이 용이하며, 특정 서비스의 변경이 다른 서비스에 미치는 영향을 최소화합니다.
*   **표준화된 API 규격:** 서비스 간 통신은 RESTful API와 JSON 형식을 표준으로 사용하여 일관성을 유지하고 통합을 용이하게 합니다.
*   **자동화된 CI/CD 파이프라인:** 코드 변경 시 빌드, 테스트, 배포 과정을 자동화하여 개발 생산성을 높이고 오류 발생 가능성을 줄입니다.
*   **중앙 집중식 로깅 및 모니터링:** 시스템 전반의 상태를 한눈에 파악하고, 문제 발생 시 신속하게 원인을 분석하고 해결할 수 있는 환경을 구축합니다.

# 2. 기술 스택 (Front, Back, DB)

본 프로젝트의 목표가 공통 아키텍처 및 데이터 모델 수립이므로, 프론트엔드 UI/UX 디자인은 제외되지만, 전체 시스템의 이해를 돕기 위해 일반적인 기술 스택을 포함합니다.

*   **Front-end:**
    *   **Framework:** React.js (또는 Vue.js)
    *   **Language:** TypeScript
    *   **Build Tool:** Vite (또는 Webpack)
    *   **State Management:** Recoil/Jotai (또는 Redux/Vuex)
    *   **UI Library:** Chakra UI (또는 Material-UI, Ant Design)
    *   **Meta-Framework (선택 사항):** Next.js (또는 Nuxt.js) - SSR/SSG 및 라우팅 기능 제공

*   **Back-end:**
    *   **Language:** Java (Enterprise 환경에서 안정성과 성능이 검증된 언어)
    *   **Framework:** Spring Boot (마이크로서비스 개발에 최적화된 강력한 생태계 제공)
    *   **API Gateway:** Spring Cloud Gateway (Spring Boot 기반 서비스와의 통합 용이)
    *   **Service Discovery:** Spring Cloud Eureka (서비스 등록 및 검색)
    *   **Configuration Server:** Spring Cloud Config (중앙 집중식 설정 관리)
    *   **Database Access:** Spring Data JPA / Hibernate (객체-관계 매핑)
    *   **Message Broker:** Apache Kafka (고성능, 고확장성 이벤트 스트리밍 플랫폼) 또는 RabbitMQ (범용 메시징)
    *   **Containerization:** Docker
    *   **Orchestration:** Kubernetes (컨테이너화된 애플리케이션의 자동 배포, 스케일링, 관리)
    *   **Monitoring:** Prometheus (메트릭 수집), Grafana (시각화)
    *   **Logging:** ELK Stack (Elasticsearch, Logstash, Kibana)

*   **Database:**
    *   **Relational Database:** PostgreSQL (강력한 ACID 트랜잭션 지원, 데이터 무결성 보장, 복잡한 쿼리 및 확장성 우수)
    *   **Caching/Session Store (선택 사항):** Redis (인메모리 데이터 스토어, 고성능 캐싱 및 세션 관리)

# 3. 데이터베이스 스키마 (주요 테이블 구조)

핵심 비즈니스 도메인인 자재, 생산, 재고, 주문에 대한 주요 테이블 구조를 정의합니다. 각 테이블은 `UUID`를 기본 키로 사용하며, 생성 및 업데이트 시각을 기록합니다.

```sql
-- 1. 자재 (Materials) 도메인

-- 자재 마스터 테이블
CREATE TABLE materials (
    material_id UUID PRIMARY KEY,
    material_code VARCHAR(100) NOT NULL UNIQUE, -- 자재 코드 (예: SKU)
    name VARCHAR(255) NOT NULL,
    description TEXT,
    unit_of_measure VARCHAR(50) NOT NULL, -- 측정 단위 (예: EA, KG, M)
    material_type VARCHAR(50) NOT NULL, -- 자재 유형 (예: RAW_MATERIAL, SEMI_FINISHED, FINISHED_GOOD)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- BOM (Bill of Materials) 테이블
CREATE TABLE bill_of_materials (
    bom_id UUID PRIMARY KEY,
    parent_material_id UUID NOT NULL REFERENCES materials(material_id), -- 상위 자재 (제품)
    component_material_id UUID NOT NULL REFERENCES materials(material_id), -- 구성 요소 자재
    quantity DECIMAL(18, 4) NOT NULL, -- 구성 요소 수량
    effective_start_date DATE,
    effective_end_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (parent_material_id, component_material_id, effective_start_date)
);

-- 2. 생산 (Production) 도메인

-- 생산 오더 테이블
CREATE TABLE production_orders (
    production_order_id UUID PRIMARY KEY,
    material_id UUID NOT NULL REFERENCES materials(material_id), -- 생산할 제품
    quantity DECIMAL(18, 4) NOT NULL, -- 생산 목표 수량
    status VARCHAR(50) NOT NULL, -- 생산 상태 (예: PLANNED, IN_PROGRESS, COMPLETED, CANCELLED)
    scheduled_start_date TIMESTAMP WITH TIME ZONE,
    scheduled_end_date TIMESTAMP WITH TIME ZONE,
    actual_start_date TIMESTAMP WITH TIME ZONE,
    actual_end_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 작업 센터 테이블 (생산이 이루어지는 장소/자원)
CREATE TABLE work_centers (
    work_center_id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    capacity DECIMAL(18, 4), -- 작업 센터의 생산 능력
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 생산 오더 작업 테이블 (생산 오더의 세부 공정)
CREATE TABLE production_order_operations (
    operation_id UUID PRIMARY KEY,
    production_order_id UUID NOT NULL REFERENCES production_orders(production_order_id),
    work_center_id UUID REFERENCES work_centers(work_center_id),
    sequence_number INT NOT NULL, -- 공정 순서
    description TEXT,
    status VARCHAR(50) NOT NULL, -- 공정 상태 (예: PENDING, RUNNING, FINISHED)
    planned_duration_minutes INT,
    actual_duration_minutes INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (production_order_id, sequence_number)
);

-- 3. 재고 (Inventory) 도메인

-- 창고 테이블
CREATE TABLE warehouses (
    warehouse_id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    location_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 재고 품목 테이블 (특정 창고의 특정 자재 재고)
CREATE TABLE inventory_items (
    inventory_item_id UUID PRIMARY KEY,
    material_id UUID NOT NULL REFERENCES materials(material_id),
    warehouse_id UUID NOT NULL REFERENCES warehouses(warehouse_id),
    quantity_on_hand DECIMAL(18, 4) NOT NULL DEFAULT 0, -- 현재 재고 수량
    batch_number VARCHAR(255), -- 배치 번호 (선택 사항)
    expiration_date DATE, -- 유통기한 (선택 사항)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (material_id, warehouse_id, batch_number) -- 배치 번호가 없으면 material_id, warehouse_id만으로 UNIQUE
);

-- 재고 트랜잭션 테이블 (재고 이동 기록)
CREATE TABLE inventory_transactions (
    transaction_id UUID PRIMARY KEY,
    inventory_item_id UUID NOT NULL REFERENCES inventory_items(inventory_item_id),
    transaction_type VARCHAR(50) NOT NULL, -- 트랜잭션 유형 (예: RECEIPT, ISSUE, ADJUSTMENT, TRANSFER)
    quantity_change DECIMAL(18, 4) NOT NULL, -- 변경된 수량 (입고는 양수, 출고는 음수)
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source_document_type VARCHAR(100), -- 원본 문서 유형 (예: SALES_ORDER, PURCHASE_ORDER, PRODUCTION_ORDER)
    source_document_id UUID, -- 원본 문서 ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. 주문 (Orders) 도메인

-- 고객 테이블 (판매 주문용)
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    email VARCHAR(255),
    phone_number VARCHAR(50),
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 공급업체 테이블 (구매 주문용)
CREATE TABLE vendors (
    vendor_id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    email VARCHAR(255),
    phone_number VARCHAR(50),
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 판매 주문 테이블
CREATE TABLE sales_orders (
    sales_order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    delivery_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL, -- 주문 상태 (예: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED)
    total_amount DECIMAL(18, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 판매 주문 품목 테이블
CREATE TABLE sales_order_items (
    sales_order_item_id UUID PRIMARY KEY,
    sales_order_id UUID NOT NULL REFERENCES sales_orders(sales_order_id),
    material_id UUID NOT NULL REFERENCES materials(material_id),
    quantity DECIMAL(18, 4) NOT NULL,
    unit_price DECIMAL(18, 4) NOT NULL,
    line_total DECIMAL(18, 4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (sales_order_id, material_id)
);

-- 구매 주문 테이블
CREATE TABLE purchase_orders (
    purchase_order_id UUID PRIMARY KEY,
    vendor_id UUID NOT NULL REFERENCES vendors(vendor_id),
    order_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    delivery_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL, -- 주문 상태 (예: PENDING, CONFIRMED, RECEIVED, CANCELLED)
    total_amount DECIMAL(18, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 구매 주문 품목 테이블
CREATE TABLE purchase_order_items (
    purchase_order_item_id UUID PRIMARY KEY,
    purchase_order_id UUID NOT NULL REFERENCES purchase_orders(purchase_order_id),
    material_id UUID NOT NULL REFERENCES materials(material_id),
    quantity DECIMAL(18, 4) NOT NULL,
    unit_price DECIMAL(18, 4) NOT NULL,
    line_total DECIMAL(18, 4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (purchase_order_id, material_id)
);
```