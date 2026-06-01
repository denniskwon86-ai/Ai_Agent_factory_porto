## 1. 전체 아키텍처 개요

본 시스템은 PRD(Product Requirements Document) 생성 및 관리를 위한 백오피스 시스템으로, 확장성과 유지보수 용이성을 최우선으로 고려하여 설계됩니다. 핵심 기능은 WBS(Work Breakdown Structure) 데이터를 기반으로 PRD를 생성하고, 사용자 피드백을 반영하여 PRD를 수정하는 것입니다.

**주요 구성 요소:**

*   **API Gateway:** 외부 요청을 받아 적절한 서비스로 라우팅하는 단일 진입점 역할을 합니다. 인증, 로깅, 속도 제한 등의 기능을 수행합니다.
*   **PRD Service:** PRD 생성, 수정, 조회 등 PRD 관련 핵심 비즈니스 로직을 담당합니다. WBS 데이터와의 연동 및 검증 로직을 포함합니다.
*   **WBS Service:** WBS 데이터를 관리하고, PRD Service에서 요청하는 WBS 정보를 제공합니다. 데이터 추출 및 검증 로직을 포함합니다.
*   **Database:** PRD 정보, WBS 메타데이터, 사용자 정보(향후 확장 고려) 등을 저장합니다.
*   **Message Queue (선택 사항):** 비동기 처리가 필요한 작업(예: 대규모 PRD 생성, 외부 시스템 연동)에 활용하여 시스템 부하를 분산하고 응답성을 향상시킵니다.

**확장성 고려 사항:**

*   **마이크로서비스 아키텍처:** 각 서비스는 독립적으로 배포 및 확장이 가능하도록 설계합니다. PRD Service와 WBS Service를 분리하여 각 기능의 부하에 따라 독립적으로 스케일링할 수 있습니다.
*   **비동기 처리:** 메시지 큐를 활용하여 시간이 오래 걸리거나 부하가 큰 작업을 비동기적으로 처리합니다.
*   **데이터베이스 샤딩/복제:** 데이터 증가에 따라 데이터베이스를 샤딩하거나 복제하여 읽기/쓰기 성능을 향상시킵니다.

**유지보수 용이성 고려 사항:**

*   **모듈화된 설계:** 각 서비스는 명확한 책임과 인터페이스를 가지도록 설계하여 코드의 이해와 수정이 용이하도록 합니다.
*   **표준화된 API:** 서비스 간 통신은 RESTful API를 표준으로 사용하여 일관성을 유지하고 통합을 용이하게 합니다.
*   **자동화된 테스트:** 단위 테스트, 통합 테스트, E2E 테스트를 자동화하여 코드 변경 시 발생할 수 있는 회귀 오류를 최소화합니다.
*   **로깅 및 모니터링:** 상세한 로깅과 실시간 모니터링 시스템을 구축하여 문제 발생 시 신속하게 원인을 파악하고 해결할 수 있도록 합니다.

**"사용자 로그인" 기능 제외:**

PRD 생성 시 "사용자 로그인" 기능이 테스트 범위에서 제외된다는 피드백을 반영하여, PRD Service는 WBS 데이터를 기반으로 PRD 내용을 생성할 때 해당 기능이 포함되지 않도록 로직을 구현합니다. 이는 WBS 데이터 자체에 해당 기능이 포함되지 않거나, PRD 생성 시 필터링 로직을 통해 제외될 수 있습니다.

## 2. 기술 스택 (Front, Back, DB)

*   **Front-end:**
    *   **Framework:** React.js (또는 Vue.js)
    *   **State Management:** Redux (또는 Vuex)
    *   **UI Library:** Material-UI (또는 Ant Design)
    *   **Build Tool:** Webpack (또는 Vite)
    *   **Language:** TypeScript

*   **Back-end:**
    *   **Language:** Java (Spring Boot) 또는 Node.js (Express.js)
    *   **Framework:** Spring Boot (Java) 또는 Express.js (Node.js)
    *   **API Gateway:** Spring Cloud Gateway (Java) 또는 Express Gateway (Node.js)
    *   **Database Access:** JPA/Hibernate (Java) 또는 Sequelize/TypeORM (Node.js)
    *   **Message Queue:** RabbitMQ 또는 Kafka (선택 사항)
    *   **Containerization:** Docker
    *   **Orchestration:** Kubernetes (확장 시 고려)

*   **Database:**
    *   **Relational Database:** PostgreSQL (또는 MySQL)
        *   ACID 트랜잭션 지원, 데이터 무결성 보장, 복잡한 쿼리 지원
    *   **NoSQL Database (선택 사항):** MongoDB (로그 저장 등 특정 용도)

## 3. 데이터베이스 스키마 (주요 테이블 구조)

```sql
-- PRD 정보 테이블
CREATE TABLE prds (
    id UUID PRIMARY KEY,
    wbs_task_id VARCHAR(255) NOT NULL UNIQUE, -- WBS 작업 ID와의 연관성
    title VARCHAR(255) NOT NULL,
    scope TEXT,
    goal TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- WBS 마스터 플랜 정보 테이블 (WBS 데이터를 저장하거나, 외부 WBS 시스템과의 연동을 위한 메타데이터 저장)
-- 실제 WBS 데이터는 외부 시스템에서 관리될 수 있으며, 여기서는 필요한 메타데이터만 저장하거나,
-- PRD 생성 시점에만 필요한 데이터를 임시로 저장할 수 있습니다.
CREATE TABLE wbs_master_plan (
    id UUID PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL UNIQUE, -- WBS 작업 ID
    task_name VARCHAR(255) NOT NULL,
    parent_task_id VARCHAR(255), -- 계층 구조를 위한 부모 작업 ID
    status VARCHAR(50), -- 예: 'TODO', 'IN_PROGRESS', 'DONE'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 현재 스프린트 작업 ID 테이블 (현재 스프린트에서 처리 중인 WBS 작업 ID 목록 관리)
CREATE TABLE current_sprint_tasks (
    id UUID PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL UNIQUE, -- WBS 작업 ID
    sprint_id VARCHAR(255) NOT NULL, -- 스프린트 식별자
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PRD 수정 이력 테이블 (선택 사항, 변경 추적을 위해)
CREATE TABLE prd_revisions (
    id UUID PRIMARY KEY,
    prd_id UUID NOT NULL REFERENCES prds(id),
    revision_number INT NOT NULL,
    title VARCHAR(255),
    scope TEXT,
    goal TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 사용자 테이블 (향후 확장 시 필요)
-- CREATE TABLE users (
--     id UUID PRIMARY KEY,
--     username VARCHAR(255) NOT NULL UNIQUE,
--     password_hash VARCHAR(255) NOT NULL,
--     role VARCHAR(50) NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
--     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );
```