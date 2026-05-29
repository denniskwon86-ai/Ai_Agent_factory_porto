### 시스템 개요
배터리 소재 생산에 필요한 자재 소요량(MRP)을 계산하고, 그 결과를 미니 대시보드를 통해 시각적으로 제공하는 시스템. 사용자에게 MRP 계산 트리거 및 결과 조회/필터링 기능을 제공한다.

### 아키텍처

#### 기술 스택
*   **백엔드**: FastAPI (Python), Pydantic, SQLAlchemy
*   **프론트엔드**: React (JavaScript/TypeScript), Chart.js / Recharts
*   **데이터베이스**: PostgreSQL / MySQL (관계형)
*   **배포**: Docker 컨테이너화, 클라우드 서비스 (AWS / Azure / GCP)

#### 컴포넌트 다이어그램 (개념)
```
+-------------------+       +-------------------+       +-------------------+
|   Frontend (React)  | <-> |   Backend (FastAPI) | <-> |   Database (SQL)    |
| - MRP Trigger UI  |     | - API Endpoints   |     | - Material Master |
| - Dashboard       |     | - MRP Calc Logic  |     | - BOM             |
| - Result View     |     | - Data Mgmt       |     | - Inventory       |
+-------------------+       +-------------------+     | - Production Plan |
                                                      | - MRP Results     |
                                                      +-------------------+
```

### 백엔드 설계

#### 주요 모듈
*   **MRP 계산 모듈**: BOM, 재고, 생산 계획 데이터를 기반으로 자재 소요량 계산 로직 구현.
*   **데이터 관리 모듈**: 자재 마스터, BOM, 재고, 생산 계획, MRP 결과 데이터의 CRUD 및 유효성 검증.
*   **API 인터페이스 모듈**: 프론트엔드와의 통신을 위한 RESTful API 엔드포인트 정의 및 처리.

#### API 엔드포인트
*   `POST /api/mrp/calculate`: MRP 계산 트리거
*   `GET /api/mrp/results`: 계산된 MRP 결과 조회 (필터링 포함)
*   `GET /api/materials`: 자재 마스터 데이터 조회
*   `GET /api/boms`: BOM 마스터 데이터 조회
*   `POST /api/materials`: 자재 마스터 데이터 생성
*   `POST /api/boms`: BOM 마스터 데이터 생성
*   `GET /api/inventory`: 재고 데이터 조회
*   `GET /api/production-plans`: 생산 계획 데이터 조회

#### 데이터 모델 (주요 엔티티)
*   **Material**: 자재 정보 (ID, 이름, 단위 등)
*   **BOM**: 자재 구성 정보 (상위 자재, 하위 자재, 소요량 등)
*   **Inventory**: 현재 재고 정보 (자재 ID, 수량, 창고 등)
*   **ProductionPlan**: 생산 계획 정보 (제품 ID, 생산량, 생산일 등)
*   **MRPResult**: MRP 계산 결과 (자재 ID, 필요 수량, 주문 시점 등)

### 프론트엔드 설계

#### 주요 화면/컴포넌트
*   **MRP 계산 트리거 화면**: MRP 계산 시작 버튼 및 관련 입력 필드 (예: 생산 계획 선택).
*   **MRP 결과 대시보드**: 계산된 MRP 결과를 요약하여 보여주는 미니 대시보드.
*   **MRP 결과 상세 조회/필터링 화면**: 특정 자재 또는 기간별 MRP 결과를 상세 조회 및 필터링 기능 제공.
*   **마스터 데이터 관리 화면**: 자재 마스터, BOM, 재고, 생산 계획 데이터 조회 및 관리 (선택적).

#### 데이터 시각화
*   Chart.js 또는 Recharts 라이브러리를 활용하여 MRP 결과 데이터를 막대 그래프, 라인 그래프, 파이 차트 등으로 시각화.
*   예: 자재별 소요량, 시간 경과에 따른 소요량 변화, 재고 대비 부족량 등.

### 데이터베이스 설계

#### 주요 테이블
*   `materials`: 자재 마스터 정보
*   `boms`: BOM 구조 정보
*   `inventory`: 현재 재고 현황
*   `production_plans`: 생산 계획
*   `mrp_results`: MRP 계산 결과

### 배포 전략
*   **컨테이너화**: 백엔드(FastAPI), 프론트엔드(React) 애플리케이션을 각각 Docker 이미지로 빌드.
*   **클라우드 배포**: AWS, Azure, 또는 GCP와 같은 클라우드 서비스에 Docker 컨테이너를 배포. (예: ECS/EKS, AKS, GKE 또는 App Service/Cloud Run)
*   **데이터베이스**: 클라우드 관리형 데이터베이스 서비스 (RDS, Azure Database, Cloud SQL) 활용.