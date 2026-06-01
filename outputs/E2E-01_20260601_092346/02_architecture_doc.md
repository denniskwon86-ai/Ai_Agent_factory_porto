# 1. 전체 아키텍처 개요

본 시스템은 **마이크로서비스 아키텍처(MSA)**를 기반으로 설계됩니다. 각 서비스는 독립적으로 개발, 배포, 확장 가능하며, 비즈니스 도메인별로 명확하게 분리됩니다.

*   **서비스 분할**: 자재 관리, 생산 관리, 재고 관리, 주문 관리 등 핵심 비즈니스 도메인을 기준으로 독립적인 마이크로서비스로 분할합니다.
*   **통신 방식**:
    *   **동기 통신**: RESTful API를 통해 서비스 간 직접적인 요청/응답 통신을 수행합니다. API Gateway를 통해 외부 요청을 받아 적절한 서비스로 라우팅합니다.
    *   **비동기 통신**: Apache Kafka 또는 RabbitMQ와 같은 메시지 브로커를 사용하여 이벤트 기반 통신을 구현합니다. 이를 통해 서비스 간의 결합도를 낮추고, 데이터 일관성을 유지하며, 장애 발생 시 복원력을 높입니다. 예를 들어, 생산 완료 이벤트는 재고 서비스에 전달되어 재고를 업데이트하는 데 사용될 수 있습니다.
*   **데이터 일관성**:
    *   **Saga 패턴**: 분산 트랜잭션을 관리하기 위해 Saga 패턴을 적용합니다. 각 서비스는 자신의 데이터를 책임지며, 다른 서비스의 데이터 변경은 비동기 메시지를 통해 조정합니다.
    *   **이벤트 소싱 (선택 사항)**: 복잡한 데이터 일관성 요구사항이 있는 경우, 이벤트 소싱 패턴을 고려하여 모든 상태 변경을 이벤트로 기록하고 이를 통해 현재 상태를 재구성할 수 있습니다.
*   **확장성**: 각 마이크로서비스는 독립적으로 확장 가능합니다. 트래픽 증가에 따라 특정 서비스만 스케일 아웃하여 리소스 효율성을 높입니다. 컨테이너화(Docker) 및 오케스트레이션(Kubernetes)을 통해 자동화된 스케일링 및 배포를 지원합니다.
*   **유지보수 용이성**: 각 서비스는 독립적인 코드베이스를 가지므로, 특정 서비스의 수정 및 배포가 다른 서비스에 미치는 영향을 최소화합니다. 명확한 API 규격과 표준화된 개발/배포 프로세스를 통해 유지보수성을 높입니다.
*   **API Gateway**: 모든 외부 요청은 API Gateway를 통해 진입하며, 인증, 인가, 라우팅, 로드 밸런싱 등의 역할을 수행합니다.
*   **서비스 디스커버리**: 서비스 인스턴스의 동적인 등록 및 검색을 위해 서비스 디스커버리 메커니즘을 사용합니다.
*   **중앙 집중식 설정 관리**: 서비스별 설정을 중앙에서 관리하여 배포 및 운영의 효율성을 높입니다.
*   **모니터링 및 로깅**: 시스템 전반의 상태를 실시간으로 파악하고 문제를 신속하게 진단하기 위해 통합 모니터링 및 로깅 시스템을 구축합니다.

# 2. 기술 스택 (Front, Back, DB)

*   **Front-end**:
    *   **Framework**: React 또는 Vue.js (SPA 개발에 적합하며, 풍부한 생태계와 컴포넌트 기반 개발 지원)
    *   **State Management**: Redux (React) 또는 Vuex (Vue.js) (애플리케이션 상태 관리)
    *   **UI Library**: Material-UI 또는 Ant Design (일관성 있고 반응형인 UI 컴포넌트 제공)
    *   **Build Tool**: Webpack 또는 Vite (모듈 번들링 및 개발 서버)
    *   **API 통신**: Axios (HTTP 클라이언트)

*   **Back-end**:
    *   **Language**: Java (안정적이고 성숙한 생태계)
    *   **Framework**: Spring Boot (마이크로서비스 개발에 최적화된 강력한 생태계 제공)
        *   **API Gateway**: Spring Cloud Gateway (Spring Boot 기반 서비스와의 통합 용이)
        *   **Service Discovery**: Spring Cloud Eureka (서비스 등록 및 검색)
        *   **Configuration Server**: Spring Cloud Config (중앙 집중식 설정 관리)
        *   **Database Access**: Spring Data JPA / Hibernate (객체-관계 매핑)
        *   **Message Broker Client**: Spring Kafka / Spring AMQP (Kafka 또는 RabbitMQ 연동)
    *   **Message Broker**: Apache Kafka (고성능, 고확장성 이벤트 스트리밍 플랫폼) 또는 RabbitMQ (범용 메시징)
    *   **Containerization**: Docker (애플리케이션 패키징 및 격리)
    *   **Orchestration**: Kubernetes (컨테이너화된 애플리케이션의 자동 배포, 스케일링, 관리)
    *   **Monitoring**: Prometheus (메트릭 수집), Grafana (시각화)
    *   **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana) 또는 Fluentd (중앙 집중식 로그 수집 및 분석)

*   **Database**:
    *   **Relational Database**: PostgreSQL (강력한 ACID 트랜잭션 지원, 데이터 무결성 보장, 복잡한 쿼리 및 확장성 우수)
    *   **Caching/Session Store (선택 사항)**: Redis (인메모리 데이터 스토어, 고성능 캐싱 및 세션 관리)

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