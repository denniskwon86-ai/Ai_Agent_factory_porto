## 기술 아키텍처 설계

### 1. 시스템 개요

본 시스템은 배터리 소재 생산을 위한 자재 소요량(MRP)을 계산하고, 계산된 결과를 시각화된 미니 대시보드를 통해 제공합니다. 백엔드는 FastAPI, 프론트엔드는 React를 사용하여 구축됩니다.

### 2. 아키텍처 다이어그램 (개념적)

```mermaid
graph TD
    A[사용자] --> B[웹 브라우저 (React App)]
    B -- API 요청 (HTTP/HTTPS) --> C[FastAPI 백엔드 서비스]
    C -- 데이터 조회/저장 --> D[데이터베이스 (PostgreSQL/MySQL)]
    C -- MRP 계산 로직 --> C
    D -- 마스터 데이터, MRP 결과 --> C
    C -- API 응답 (JSON) --> B
    B -- 대시보드 렌더링 --> A
```

### 3. 주요 컴포넌트

*   **프론트엔드 (React Application)**
    *   **역할**: 사용자 인터페이스 제공, MRP 계산 요청, 계산 결과 시각화 (미니 대시보드).
    *   **기술 스택**: React, JavaScript/TypeScript, HTML, CSS, 차트 라이브러리 (예: Chart.js, Recharts).
    *   **주요 기능**:
        *   자재 소요량 계산 트리거 UI
        *   계산된 MRP 데이터 조회 및 필터링
        *   미니 대시보드 (그래프, 차트)를 통한 시각화
        *   백엔드 API와의 통신 관리

*   **백엔드 (FastAPI Service)**
    *   **역할**: 핵심 비즈니스 로직 (MRP 계산), 데이터 관리, 프론트엔드에 API 제공.
    *   **기술 스택**: FastAPI (Python), Pydantic (데이터 유효성 검사), SQLAlchemy/ORM (데이터베이스 연동).
    *   **주요 기능**:
        *   **MRP 계산 모듈**: BOM(Bill of Materials), 재고 현황, 생산 계획 등을 기반으로 자재 소요량 계산 로직 구현.
        *   **API 엔드포인트**:
            *   `/api/mrp/calculate`: MRP 계산 요청 (POST)
            *   `/api/mrp/results`: 계산된 MRP 결과 조회 (GET)
            *   `/api/materials`: 자재 마스터 데이터 조회 (GET)
            *   `/api/boms`: BOM 데이터 조회 (GET)
        *   **데이터베이스 연동**: 자재 마스터, BOM, 재고, 생산 계획, MRP 계산 결과 저장 및 조회.
        *   **에러 처리 및 로깅**: 안정적인 서비스 운영을 위한 기능.

*   **데이터베이스 (Database)**
    *   **역할**: 시스템 운영에 필요한 모든 데이터 저장 및 관리.
    *   **기술 스택**: 관계형 데이터베이스 (예: PostgreSQL, MySQL) 권장.
    *   **주요 데이터**:
        *   자재 마스터 (Material Master): 자재 정보, 단위, 리드 타임 등
        *   BOM (Bill of Materials): 제품 구성 정보
        *   재고 현황 (Inventory): 현재 재고량
        *   생산 계획 (Production Plan): 생산 목표량 및 일정
        *   MRP 계산 결과: 각 자재별 소요량, 발주 시점 등

### 4. 데이터 흐름

1.  사용자가 React 애플리케이션을 통해 MRP 계산을 요청합니다.
2.  React 애플리케이션은 FastAPI 백엔드의 `/api/mrp/calculate` 엔드포인트로 HTTP POST 요청을 보냅니다.
3.  FastAPI 백엔드는 요청을 수신하고, 데이터베이스에서 필요한 자재 마스터, BOM, 재고, 생산 계획 데이터를 조회합니다.
4.  FastAPI 백엔드는 조회된 데이터를 기반으로 MRP 계산 로직을 수행하고, 계산된 결과를 데이터베이스에 저장합니다.
5.  계산 완료 후, FastAPI 백엔드는 성공 응답을 React 애플리케이션에 반환합니다.
6.  사용자가 React 애플리케이션을 통해 MRP 결과를 조회하면, React는 `/api/mrp/results` 엔드포인트로 HTTP GET 요청을 보냅니다.
7.  FastAPI 백엔드는 데이터베이스에서 MRP 계산 결과를 조회하여 JSON 형태로 React 애플리케이션에 반환합니다.
8.  React 애플리케이션은 수신된 데이터를 파싱하여 미니 대시보드에 시각화하여 사용자에게 표시합니다.

### 5. 핵심 기술 요구사항 반영

*   **FastAPI (백엔드)**: 고성능 비동기 API 개발에 최적화되어 MRP 계산 및 데이터 처리를 효율적으로 수행합니다.
*   **React (프론트엔드)**: 컴포넌트 기반의 UI 개발을 통해 직관적이고 반응성 높은 미니 대시보드를 구축합니다.

### 6. 추가 고려사항

*   **배포 (Deployment)**: Docker를 이용한 컨테이너화 및 Kubernetes 또는 클라우드 서비스 (AWS ECS/EKS, Azure AKS, GCP GKE/Cloud Run)를 활용한 배포를 고려합니다.
*   **인증 및 권한 (Authentication & Authorization)**: 사용자 로그인 및 역할 기반 접근 제어가 필요한 경우, FastAPI에서 JWT(JSON Web Token) 등을 활용하여 구현합니다.
*   **모니터링 및 로깅**: 시스템의 성능 및 안정성 확보를 위해 모니터링 도구(Prometheus, Grafana) 및 중앙 집중식 로깅 시스템(ELK Stack) 도입을 고려합니다.
*   **확장성 (Scalability)**: FastAPI는 비동기 처리로 높은 동시성을 지원하며, 필요시 여러 인스턴스를 실행하여 수평 확장이 가능합니다. React 애플리케이션은 CDN을 통해 배포하여 성능을 최적화할 수 있습니다.