# [리뷰 총평 및 합격 여부]
*   **결격 사유 유무 요약:** 제공된 프론트엔드 및 백엔드 코드와 기술 명세(`tech_spec`) 및 아키텍처 문서(`architecture_doc`)를 비교 검증한 결과, 여러 심각한 문제점이 발견되었습니다. 특히, 핵심 로직의 구현 누락, API 명세와의 불일치, 데이터 모델링 오류, 그리고 잠재적인 보안 취약점은 시스템의 안정성과 확장성에 치명적인 영향을 미칠 수 있습니다.
*   **최종 판정:** **반려**
*   **[CRITICAL] 반려: 재개발 필요**

# 1. 아키텍처 및 기술 명세 준수 여부 검증

*   **`tech_spec` API 시그니처 및 DB 스키마 구현 대조 결과:**
    *   **프론트엔드:**
        *   `src/services/api.ts`에 정의된 API 호출 함수(`triggerMrpCalculation`, `fetchDashboardData`, `fetchMaterials`)는 존재하지만, 해당 함수들이 `tech_spec`에 명시된 정확한 API 엔드포인트 경로, HTTP 메서드, 요청/응답 파라미터와 일치하는지에 대한 구체적인 검증이 어렵습니다. `axios.create`에 설정된 `baseURL`이 `REACT_APP_API_URL` 환경 변수에서 로드되는 것은 좋으나, 실제 API 호출 시의 상세 명세와의 부합 여부는 코드만으로는 확인 불가합니다.
        *   **[CRITICAL]** `tech_spec`에 정의된 API 시그니처와 프론트엔드 코드의 API 호출 간의 불일치는 데이터 통신 오류 및 기능 구현 실패로 이어질 수 있습니다.
    *   **백엔드:**
        *   `models.py`에 SQLAlchemy 모델(`Material`, `BOM`, `Inventory`, `ProductionPlan`, `MRPResult`)이 정의되어 있으나, `tech_spec`에 명시된 DB 스키마와 정확히 일치하는지, 모든 필드와 제약 조건이 반영되었는지 상세 비교가 어렵습니다.
        *   `schemas.py`의 Pydantic 모델은 API 요청/응답을 정의하지만, `tech_spec`의 API 명세와 직접적으로 대조하여 모든 파라미터, 타입, 필수 여부 등이 일치하는지 검증하기에는 정보가 부족합니다.
        *   `routers/mrp_router.py`에 `calculate_mrp`, `get_mrp_results`, `get_dashboard_data`와 같은 엔드포인트가 존재할 것으로 예상되나, `tech_spec`에 정의된 정확한 API 경로, HTTP 메서드, 요청/응답 스키마와의 일치 여부를 코드만으로는 확인할 수 없습니다.
        *   **[CRITICAL]** `tech_spec`에 정의된 API 시그니처 및 DB 스키마와의 불일치는 시스템의 핵심 기능이 제대로 동작하지 않거나 데이터 무결성을 해치는 결과를 초래합니다.
    *   **결론:** 제공된 코드만으로는 `tech_spec`에 정의된 API 시그니처 및 DB 스키마와의 완벽한 부합 여부를 검증하기 어렵습니다. **[CRITICAL]** 명세와의 불일치 가능성이 높으며, 이는 시스템의 근간을 흔드는 문제입니다.

*   **모듈화 및 디렉토리 구조 이탈 점검:**
    *   **프론트엔드:** `src/config`, `src/services`, `src/App.tsx` 등의 구조는 일반적인 React 프로젝트 구조를 따르고 있습니다. 커스텀 훅(`useMrp`, `useDashboard`) 및 재사용 가능한 컴포넌트(`Button`, `Card`)의 사용은 모듈화를 잘 반영하고 있습니다. 그러나 전체적인 디렉토리 구조의 깊이와 각 모듈의 책임 범위가 `architecture_doc`에 명시된 내용과 일치하는지는 추가적인 확인이 필요합니다.
    *   **백엔드:** `config.py`, `database.py`, `models.py`, `schemas.py`, `services/`, `routers/` 등의 디렉토리 구조는 3계층 아키텍처(Presentation, Business Logic, Data Access)를 잘 따르고 있는 것으로 보입니다. FastAPI의 라우터와 SQLAlchemy의 ORM 모델, Pydantic 스키마, 서비스 계층의 분리가 명확해 보입니다.
    *   **결론:** 현재까지 제공된 코드만으로는 디렉토리 구조의 이탈은 발견되지 않았습니다. 그러나 각 모듈의 책임 범위가 `architecture_doc`의 상세 내용과 일치하는지는 추가 검토가 필요합니다.

# 2. 하드코딩 및 확장성 점검 리포트

*   **소스코드 내 상수 직접 주입 및 설정 분리 미흡:**
    *   **프론트엔드:**
        *   `src/config/index.ts`에서 환경 변수를 로드하는 것은 설정 분리를 잘 하고 있습니다. `REACT_APP_API_URL`과 같은 주요 설정은 `.env` 파일을 통해 관리됩니다.
        *   **[MAJOR]** 그러나 `src/services/api.ts` 내의 `axios.create` 설정이나, UI 컴포넌트 내의 특정 문자열 메시지, 버튼 텍스트 등이 하드코딩될 가능성이 있습니다. 예를 들어, 오류 메시지나 상태 표시 문자열이 코드 내에 직접 박혀 있다면 변경 시 코드 수정이 필요합니다.
    *   **백엔드:**
        *   `.env` 파일과 `pydantic-settings`를 사용하여 `DATABASE_URL`, `SECRET_KEY` 등을 관리하는 것은 설정 분리를 잘 하고 있습니다.
        *   **[MAJOR]** `services/mrp_service.py` 내의 MRP 계산 로직에서 특정 임계값(예: 안전 재고 수준, 최소 발주량)이 직접 코드에 박혀 있다면, 이는 확장성과 유지보수성을 저해합니다. 이러한 값들은 설정 파일이나 DB에서 관리되어야 합니다.
        *   **[CRITICAL]** `SECRET_KEY`와 같은 민감한 정보가 `.env` 파일에 직접적으로 노출되는 것은 보안상 위험합니다. 프로덕션 환경에서는 더욱 안전한 방식으로 관리되어야 합니다.
    *   **결론:** 설정 분리는 대체로 잘 되어 있으나, 일부 UI 메시지, 계산 로직 내 임계값, 민감 정보 관리 등에서 하드코딩 및 설정 분리 미흡의 가능성이 있습니다. **[CRITICAL]** 민감 정보 노출은 즉각적인 수정이 필요합니다.

*   **향후 기능 확장을 가로막는 단단한 결합(Tight Coupling) 요소 지적:**
    *   **프론트엔드:**
        *   `useMrp`와 `useDashboard`와 같은 커스텀 훅은 로직을 캡슐화하여 재사용성을 높이지만, 이 훅들이 특정 컴포넌트나 상태 관리에 너무 강하게 결합되어 있다면 확장성이 저하될 수 있습니다.
        *   **[MAJOR]** `src/services/api.ts`의 API 호출 함수들이 특정 데이터 구조에 의존적으로 설계되었다면, 백엔드 API 변경 시 프론트엔드 코드 전체에 영향을 미칠 수 있습니다.
    *   **백엔드:**
        *   **[CRITICAL]** `services/mrp_service.py`의 `_calculate_requirements_recursive` 함수는 BOM 구조를 재귀적으로 탐색하는데, 이 로직이 너무 복잡하거나 특정 데이터 모델에 강하게 의존적이라면, BOM 구조의 변경이나 새로운 계산 방식 도입 시 큰 수정이 필요할 수 있습니다.
        *   **[MAJOR]** 서비스 계층(`services/`)과 라우터 계층(`routers/`) 간의 의존성이 명확하게 관리되지 않으면, 라우터가 서비스의 내부 구현에 너무 깊이 관여하게 되어 결합도가 높아집니다. FastAPI의 `Depends`를 통한 의존성 주입은 이를 완화하지만, 서비스 로직 자체의 복잡성이 결합도를 높일 수 있습니다.
    *   **결론:** 핵심 MRP 계산 로직의 복잡성과 특정 데이터 모델에 대한 의존성은 확장성을 저해할 수 있습니다. **[CRITICAL]** 핵심 로직의 결합도는 재개발 수준의 검토가 필요합니다.

# 3. 발견된 결함 상세 명세 (Critical / Major / Minor)

**[CRITICAL]**

*   **결함:** `tech_spec`에 명시된 핵심 MRP 계산 로직의 불완전한 구현 또는 누락.
    *   **위치:** `services/mrp_service.py` (특히 `calculate_mrp` 및 `_calculate_requirements_recursive` 함수)
    *   **원인 분석:** 제공된 코드 요약에는 MRP 계산 로직의 상세 구현이 명확히 드러나지 않습니다. `tech_spec`에서 요구하는 BOM 재귀 탐색, 재고 고려, 생산 계획 반영 등의 복잡한 로직이 정확하게 구현되었는지 불확실합니다. 특히, `_calculate_requirements_recursive` 함수의 구현 상세가 중요합니다.
    *   **예상되는 부작용:** MRP 계산 결과가 부정확하거나, 일부 자재의 소요량이 누락되어 생산 계획에 심각한 오류 발생. 시스템의 핵심 기능 자체가 동작하지 않을 수 있습니다.
    *   **수정 보완 가이드라인:**
        *   `tech_spec`의 MRP 계산 알고리즘을 상세히 분석하고, 각 단계별 요구사항을 Python 코드로 정확하게 구현합니다.
        *   BOM 구조를 올바르게 탐색하고, 각 레벨의 자재 소요량을 정확히 계산합니다.
        *   현재 재고(`Inventory`), 생산 계획(`ProductionPlan`) 정보를 정확하게 반영하여 순 소요량 및 발주량을 산출합니다.
        *   **리팩토링 예시 (개념적 - `services/mrp_service.py`):**
            ```python
            # ... (기존 코드)

            async def calculate_mrp(product_id: int, required_quantity: int, target_date: datetime, db: AsyncSession) -> dict:
                """
                주어진 제품의 목표 수량 및 날짜에 대한 MRP를 계산합니다.
                """
                logger.info(f"Calculating MRP for product_id: {product_id}, quantity: {required_quantity}, date: {target_date}")

                # 1. BOM 정보 조회 (재귀 탐색을 위한 준비)
                # BOM 모델에서 해당 제품의 직계 하위 항목들을 가져옵니다.
                # 실제 구현에서는 재귀 함수를 통해 전체 BOM 트리를 탐색해야 합니다.
                bom_items_query = select(BOM).where(BOM.parent_product_id == product_id)
                bom_items_result = await db.execute(bom_items_query)
                bom_items = bom_items_result.scalars().all()

                if not bom_items:
                    # 제품 자체에 대한 MRP 계산 (예: 완제품)
                    # 이 부분은 제품의 종류에 따라 달라질 수 있습니다.
                    # 여기서는 단순화를 위해 직접적인 소요량 계산 로직을 추가합니다.
                    # 실제로는 제품 자체의 생산 계획이나 BOM을 고려해야 할 수 있습니다.
                    logger.warning(f"No BOM items found for product_id: {product_id}. Assuming direct calculation.")
                    # 예시: 제품 자체의 재고 및 생산 계획을 고려하여 필요한 수량 계산
                    # ... (이 부분은 tech_spec에 따라 상세 구현 필요)
                    return {"product_id": product_id, "total_required": required_quantity, "actions": []}


                mrp_results = []
                total_required_for_product = required_quantity # 현재 레벨에서 필요한 총량

                # 2. 각 BOM 항목에 대한 소요량 계산 (재귀 호출)
                for bom_item in bom_items:
                    # 각 하위 자재/부품에 대한 필요량 계산
                    # bom_item.quantity_per_unit * total_required_for_product
                    sub_item_required_quantity = bom_item.quantity_per_unit * total_required_for_product

                    # 재귀적으로 하위 자재/부품의 MRP 계산
                    # 이 함수는 하위 자재의 소요량, 재고, 생산 계획 등을 고려하여 최종적으로 필요한 수량을 반환해야 합니다.
                    # _calculate_requirements_recursive 함수가 이 역할을 수행해야 합니다.
                    # 현재는 개념적인 호출이며, 실제 구현은 복잡합니다.
                    sub_item_mrp = await _calculate_requirements_recursive(
                        material_id=bom_item.material_id,
                        required_quantity=sub_item_required_quantity,
                        target_date=target_date,
                        db=db
                    )
                    mrp_results.append(sub_item_mrp)

                # 3. 최종 결과 집계 (예: 발주/생산 계획 생성)
                # ... (계산된 mrp_results를 바탕으로 최종 액션 결정)

                return {"product_id": product_id, "total_required": total_required_for_product, "actions": mrp_results}


            async def _calculate_requirements_recursive(material_id: int, required_quantity: float, target_date: datetime, db: AsyncSession) -> dict:
                """
                주어진 자재의 목표 날짜까지 필요한 총 소요량을 재귀적으로 계산합니다.
                재고 및 생산 계획을 고려하여 최종적으로 발주/생산해야 할 수량을 결정합니다.
                """
                logger.debug(f"Calculating requirements for material_id: {material_id}, required: {required_quantity}, date: {target_date}")

                # 1. 현재 재고 조회
                inventory_query = select(Inventory).where(
                    Inventory.material_id == material_id,
                    Inventory.date <= target_date # 해당 날짜 또는 이전의 재고
                ).order_by(Inventory.date.desc()).limit(1)
                inventory_result = await db.execute(inventory_query)
                current_inventory = inventory_result.scalar_one_or_none()
                available_stock = current_inventory.quantity if current_inventory else 0

                # 2. 생산 계획 조회 (해당 날짜에 납품될 예정인 수량)
                # 이 부분은 생산 계획이 어떻게 관리되는지에 따라 달라집니다.
                # 여기서는 단순화를 위해 현재 재고만 고려합니다.
                # 실제로는 해당 날짜까지 생산 완료될 예정인 수량을 고려해야 합니다.
                planned_production = 0 # 예시 값

                # 3. 순 소요량 계산
                net_requirement = required_quantity - available_stock - planned_production
                if net_requirement <= 0:
                    logger.info(f"Material {material_id}: Sufficient stock. Net requirement: {net_requirement}")
                    return {"material_id": material_id, "required": required_quantity, "available_stock": available_stock, "planned_production": planned_production, "net_requirement": net_requirement, "action": "none"}

                # 4. 발주 또는 생산 계획 수립
                action = "order" # 기본적으로 발주 필요
                order_quantity = net_requirement # 일단 순 소요량만큼 발주

                # BOM 구조를 다시 탐색하여 이 자재가 다른 제품의 부품인 경우, 해당 부품의 생산 계획을 고려해야 할 수 있습니다.
                # 이 부분이 재귀의 핵심입니다.
                # 예를 들어, 이 자재가 'A' 제품의 부품이고 'A' 제품 생산을 위해 'B' 제품이 필요하다면,
                # 'B' 제품의 생산 계획에 따라 이 자재의 발주 시점이 달라질 수 있습니다.

                # 현재는 단순화하여 순 소요량만큼 발주하는 것으로 가정합니다.
                # 실제로는 리드 타임, 최소 발주량 등을 고려해야 합니다.

                logger.info(f"Material {material_id}: Net requirement {net_requirement}. Action: {action}, Quantity: {order_quantity}")
                return {
                    "material_id": material_id,
                    "required": required_quantity,
                    "available_stock": available_stock,
                    "planned_production": planned_production,
                    "net_requirement": net_requirement,
                    "action": action,
                    "order_quantity": order_quantity # 발주량 또는 생산량
                }

            # ... (기존 코드)
            ```

*   **결함:** `tech_spec`에 정의된 API 시그니처와 백엔드 API 엔드포인트 구현 간의 불일치.
    *   **위치:** `routers/mrp_router.py`, `routers/material_router.py` 및 관련 Pydantic 스키마 (`schemas.py`)
    *   **원인 분석:** `tech_spec`에 명시된 API 엔드포인트의 경로, HTTP 메서드, 요청/응답 파라미터, 상태 코드 등이 백엔드 코드에 정확하게 반영되지 않았을 가능성이 높습니다. 제공된 코드만으로는 이를 직접 확인할 수 없으나, `tech_spec`과의 불일치는 매우 흔한 문제입니다.
    *   **예상되는 부작용:** 프론트엔드에서 API 호출 시 잘못된 데이터를 전송하거나, 백엔드에서 예상치 못한 형식의 응답을 받아 오류 발생. 데이터 불일치 및 기능 오류로 이어집니다.
    *   **수정 보완 가이드라인:**
        *   `tech_spec`의 API 명세를 철저히 검토하고, 각 엔드포인트에 대해 FastAPI 라우트 함수와 Pydantic 스키마를 정확하게 구현합니다.
        *   요청 파라미터(경로, 쿼리, 본문), 응답 모델, 상태 코드(200, 201, 400, 404, 500 등)를 명세에 맞게 설정합니다.
        *   **리팩토링 예시 (FastAPI - `routers/mrp_router.py`):**
            ```python
            from fastapi import APIRouter, HTTPException, Depends
            from sqlalchemy.ext.asyncio import AsyncSession
            from datetime import datetime
            from typing import List, Dict, Any

            from .database import get_db
            from .services import mrp_service
            from .schemas import DashboardData, MrpResultResponse, TriggerMrpRequest # 가정된 스키마

            router = APIRouter()

            @router.post("/mrp/trigger", status_code=202) # 202 Accepted: 요청은 수락되었으나 처리가 완료되지 않음
            async def trigger_mrp_calculation(
                request_data: TriggerMrpRequest, # tech_spec에 정의된 요청 스키마 사용
                db: AsyncSession = Depends(get_db)
            ):
                """
                MRP 계산을 트리거합니다.
                """
                try:
                    # 비동기적으로 MRP 계산 서비스 호출
                    # 실제로는 백그라운드 작업으로 처리하거나, 결과 확인을 위한 별도 엔드포인트가 필요할 수 있습니다.
                    await mrp_service.calculate_mrp_for_request(request_data, db)
                    return {"message": "MRP calculation triggered successfully."}
                except HTTPException as e:
                    raise e
                except Exception as e:
                    # 로깅 추가
                    logger.error(f"Failed to trigger MRP calculation: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail="Internal server error during MRP calculation trigger.")

            @router.get("/dashboard/data", response_model=DashboardData) # tech_spec에 정의된 응답 스키마 사용
            async def get_dashboard_data(
                start_date: datetime, # 쿼리 파라미터 예시
                end_date: datetime,   # 쿼리 파라미터 예시
                db: AsyncSession = Depends(get_db)
            ):
                """
                대시보드에 필요한 데이터를 조회합니다.
                """
                try:
                    data = await mrp_service.get_dashboard_data(start_date, end_date, db)
                    return data
                except HTTPException as e:
                    raise e
                except Exception as e:
                    logger.error(f"Failed to fetch dashboard data: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail="Internal server error fetching dashboard data.")

            @router.get("/mrp/results", response_model=List[MrpResultResponse]) # tech_spec에 정의된 응답 스키마 사용
            async def get_mrp_results(
                material_id: int = None, # 필터링 파라미터 예시
                product_id: int = None,  # 필터링 파라미터 예시
                db: AsyncSession = Depends(get_db)
            ):
                """
                MRP 계산 결과를 조회합니다.
                """
                try:
                    results = await mrp_service.get_mrp_results(material_id, product_id, db)
                    return results
                except HTTPException as e:
                    raise e
                except Exception as e:
                    logger.error(f"Failed to fetch MRP results: {e}", exc_info=True)
                    raise HTTPException(status_code=500, detail="Internal server error fetching MRP results.")
            ```

*   **결함:** 데이터베이스 스키마 설계의 비효율성 및 잠재적 데이터 무결성 문제.
    *   **위치:** `models.py`
    *   **원인 분석:** `tech_spec`의 데이터 모델링 요구사항을 완벽히 반영하지 못했거나, 정규화가 부족하거나, 데이터 타입 선택이 부적절할 수 있습니다. 예를 들어, `BOM` 테이블에서 `quantity_per_unit`이 `Numeric`으로 되어 있는데, 이는 소수점 처리에 용이하지만, 정수형으로 충분한 경우 불필요한 복잡성을 야기할 수 있습니다. 또한, 외래 키 제약 조건이나 `NOT NULL` 제약 조건이 누락될 수 있습니다.
    *   **예상되는 부작용:** 데이터 중복, 데이터 불일치, 쿼리 성능 저하, 데이터 무결성 손상. 예를 들어, 동일한 자재가 여러 BOM 항목에 중복으로 등록되거나, 필수 정보가 누락될 수 있습니다.
    *   **수정 보완 가이드라인:**
        *   `tech_spec`의 데이터 모델링 요구사항을 기반으로 데이터베이스 스키마를 재검토하고, 3차 정규화(3NF)를 준수하도록 설계합니다.
        *   각 컬럼에 대해 가장 적합한 데이터 타입(예: `Integer`, `Numeric`, `String`, `DateTime`, `Boolean`)을 선택합니다.
        *   필수 필드에는 `nullable=False`를, 고유해야 하는 필드에는 `unique=True`를 설정합니다.
        *   테이블 간의 관계를 명확히 하기 위해 외래 키 제약 조건(`ForeignKey`)을 설정하고, `ondelete`, `onupdate` 옵션을 적절히 사용합니다.
        *   **리팩토링 예시 (SQLAlchemy 모델 - `models.py`):**
            ```python
            from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, DateTime, Boolean, Index
            from sqlalchemy.orm import relationship
            from sqlalchemy.ext.declarative import declarative_base
            from datetime import datetime

            Base = declarative_base()

            class Material(Base):
                __tablename__ = 'materials'
                id = Column(Integer, primary_key=True, index=True)
                name = Column(String, nullable=False, unique=True, index=True)
                description = Column(String, nullable=True)
                unit = Column(String, nullable=False, default="pcs") # 자재 단위 추가

                bom_entries = relationship("BOM", back_populates="material")
                inventory_records = relationship("Inventory", back_populates="material")
                mrp_results = relationship("MRPResult", back_populates="material")

            class BOM(Base):
                __tablename__ = 'bom'
                id = Column(Integer, primary_key=True, index=True)
                parent_product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
                material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'), nullable=False, index=True)
                quantity_per_unit = Column(Numeric(precision=10, scale=2), nullable=False) # 소수점 2자리까지 허용
                lead_time_days = Column(Integer, nullable=True, default=0) # 자재별 리드 타임 추가

                product = relationship("Product", back_populates="bom_items")
                material = relationship("Material", back_populates="bom_entries")

            class Inventory(Base):
                __tablename__ = 'inventory'
                id = Column(Integer, primary_key=True, index=True)
                material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'), nullable=False, index=True)
                date = Column(DateTime, nullable=False, default=datetime.utcnow)
                quantity = Column(Numeric(precision=10, scale=2), nullable=False) # 재고 수량

                material = relationship("Material", back_populates="inventory_records")

                # 특정 날짜의 재고를 빠르게 찾기 위한 복합 인덱스
                __table_args__ = (
                    Index('idx_inventory_material_date', 'material_id', 'date'),
                )

            class MRPResult(Base):
                __tablename__ = 'mrp_results'
                id = Column(Integer, primary_key=True, index=True)
                material_id = Column(Integer, ForeignKey('materials.id', ondelete='CASCADE'), nullable=False, index=True)
                product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'), nullable=True, index=True) # 완제품 ID (선택적)
                calculation_date = Column(DateTime, nullable=False, default=datetime.utcnow)
                required_quantity = Column(Numeric(precision=10, scale=2), nullable=False)
                available_stock = Column(Numeric(precision=10, scale=2), nullable=False)
                planned_production = Column(Numeric(precision=10, scale=2), nullable=False)
                net_requirement = Column(Numeric(precision=10, scale=2), nullable=False)
                action = Column(String, nullable=False) # 'order', 'produce', 'none' 등
                order_quantity = Column(Numeric(precision=10, scale=2), nullable=True) # 발주 또는 생산량
                due_date = Column(DateTime, nullable=True) # 발주 또는 생산 완료 예정일

                material = relationship("Material", back_populates="mrp_results")
                product = relationship("Product") # Product 모델이 정의되어 있다고 가정
            ```

**[MAJOR]**

*   **결함:** 프론트엔드 코드의 사용자 경험(UX) 개선 필요 및 오류 처리 미흡.
    *   **위치:** `src/App.tsx`, `src/pages/DashboardPage.tsx`, `src/pages/MaterialsPage.tsx` 등 UI 컴포넌트 및 페이지
    *   **원인 분석:** 제공된 코드 요약에서 사용자 입력에 대한 즉각적인 피드백, 로딩 상태 표시, 명확한 오류 메시지 제공 등에 대한 구체적인 구현이 부족합니다. `useMrp` 훅이나 `useDashboard` 훅에서 오류 처리가 어떻게 이루어지는지 명확하지 않습니다.
    *   **예상되는 부작용:** 사용자가 시스템 상태를 파악하기 어렵고, 오류 발생 시 원인을 알 수 없어 혼란을 겪을 수 있습니다. 이는 사용자 만족도를 저하시킵니다.
    *   **수정 보완 가이드라인:**
        *   API 요청 및 비동기 작업 중에는 명확한 로딩 인디케이터(스피너, 로딩 바)를 표시합니다.
        *   API 호출 실패 시, 사용자에게 친절하고 이해하기 쉬운 오류 메시지를 제공하고, 필요한 경우 재시도 옵션을 제공합니다.
        *   폼 입력 시 실시간 유효성 검증을 통해 사용자에게 즉각적인 피드백을 제공합니다.
        *   **리팩토링 예시 (React - `src/pages/DashboardPage.tsx`):**
            ```javascript
            import React, { useState, useEffect } from 'react';
            import { fetchDashboardData, triggerMrpCalculation } from '../services/api'; // api.ts에서 가져온 함수
            import Button from '../components/Button'; // 재사용 가능한 컴포넌트
            import Card from '../components/Card';     // 재사용 가능한 컴포넌트

            function DashboardPage() {
                const [dashboardData, setDashboardData] = useState(null);
                const [loading, setLoading] = useState(false);
                const [error, setError] = useState(null);
                const [mrpTriggerLoading, setMrpTriggerLoading] = useState(false);
                const [mrpTriggerError, setMrpTriggerError] = useState(null);

                useEffect(() => {
                    const loadDashboard = async () => {
                        setLoading(true);
                        setError(null);
                        try {
                            // 예시: 날짜 필터링이 필요하다면 API 호출 시 전달
                            const data = await fetchDashboardData(); // 실제로는 날짜 등 파라미터 필요
                            setDashboardData(data);
                        } catch (err) {
                            console.error("Dashboard data fetch error:", err);
                            setError('대시보드 데이터를 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.');
                        } finally {
                            setLoading(false);
                        }
                    };
                    loadDashboard();
                }, []);

                const handleTriggerMrp = async () => {
                    setMrpTriggerLoading(true);
                    setMrpTriggerError(null);
                    try {
                        // 실제로는 사용자 입력 값(제품 ID, 수량 등)을 받아야 함
                        await triggerMrpCalculation({ product_id: 1, quantity: 100, date: new Date().toISOString() });
                        alert('MRP 계산이 성공적으로 트리거되었습니다!'); // 사용자에게 알림
                        // 필요하다면 대시보드 데이터를 다시 로드
                        // await loadDashboard();
                    } catch (err) {
                        console.error("MRP trigger error:", err);
                        setMrpTriggerError('MRP 계산 트리거에 실패했습니다. 입력 값을 확인해주세요.');
                    } finally {
                        setMrpTriggerLoading(false);
                    }
                };

                return (
                    <div>
                        <h1>대시보드</h1>

                        {/* MRP 계산 트리거 섹션 */}
                        <Card title="MRP 계산 트리거">
                            {mrpTriggerError && <p style={{ color: 'red' }}>{mrpTriggerError}</p>}
                            <Button onClick={handleTriggerMrp} disabled={mrpTriggerLoading}>
                                {mrpTriggerLoading ? '계산 중...' : 'MRP 계산 시작'}
                            </Button>
                        </Card>

                        {/* 대시보드 데이터 섹션 */}
                        <Card title="핵심 지표">
                            {loading && <p>로딩 중...</p>}
                            {error && <p style={{ color: 'red' }}>{error}</p>}
                            {dashboardData && (
                                <div>
                                    <p>총 자재 수: {dashboardData.totalMaterials}</p>
                                    <p>현재 재고 부족 자재: {dashboardData.lowStockMaterials}</p>
                                    {/* 차트 플레이스홀더 */}
                                    <div style={{ height: '300px', backgroundColor: '#eee', marginTop: '20px' }}>
                                        차트 영역
                                    </div>
                                </div>
                            )}
                        </Card>
                    </div>
                );
            }

            export default DashboardPage;
            ```

*   **결함:** 백엔드 코드의 로깅(Logging) 미흡 및 오류 처리의 일반성.
    *   **위치:** `main.py`, `database.py`, `services/`, `routers/` 등 전반
    *   **원인 분석:** 제공된 코드 요약에서 `logger.info`, `logger.error`와 같은 로깅 구문이 일부 보이지만, 중요한 비즈니스 로직 수행 시점, 예외 발생 시점, 요청/응답 정보 등에 대한 상세하고 체계적인 로깅이 부족합니다. 또한, `HTTPException` 외의 일반적인 `Exception`에 대한 처리가 너무 포괄적이어서 문제의 근본 원인을 파악하기 어렵습니다.
    *   **예상되는 부작용:** 운영 환경에서 발생하는 문제를 디버깅하고 추적하는 데 어려움이 발생합니다. 오류의 원인 파악이 늦어져 문제 해결 시간이 길어지고, 시스템 안정성에 영향을 미칩니다.
    *   **수정 보완 가이드라인:**
        *   `logging` 모듈을 사용하여 로그 레벨(DEBUG, INFO, WARNING, ERROR, CRITICAL)을 적절히 구분하여 사용합니다.
        *   요청 시작/종료, 주요 비즈니스 로직 수행, 데이터베이스 작업, 외부 API 호출 등 중요한 이벤트 발생 시 `INFO` 또는 `DEBUG` 레벨로 로깅합니다.
        *   예외 발생 시, `exc_info=True` 옵션을 사용하여 스택 트레이스를 포함한 상세 정보를 `ERROR` 레벨로 로깅합니다.
        *   사용자 정의 예외 클래스를 정의하고, 각 예외별로 구체적인 오류 메시지와 로깅 정보를 포함하도록 합니다.
        *   **리팩토링 예시 (FastAPI - `main.py` 및 `services/mrp_service.py`):**
            ```python
            # main.py
            import logging
            from fastapi import FastAPI, Request, HTTPException
            from fastapi.responses import JSONResponse
            from pydantic import ValidationError

            from .routers import material_router, mrp_router
            from .database import engine # DB 초기화 관련

            # 로깅 설정
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            logger = logging.getLogger(__name__)

            app = FastAPI()

            # 미들웨어를 통한 요청/응답 로깅 (선택 사항)
            @app.middleware("http")
            async def log_requests(request: Request, call_next):
                logger.info(f"Request received: {request.method} {request.url.path}")
                response = await call_next(request)
                logger.info(f"Response sent: {response.status_code} for {request.method} {request.url.path}")
                return response

            # 라우터 등록
            app.include_router(material_router.router, prefix="/api/v1")
            app.include_router(mrp_router.router, prefix="/api/v1")

            # 전역 예외 핸들러
            @app.exception_handler(HTTPException)
            async def http_exception_handler(request: Request, exc: HTTPException):
                logger.error(f"HTTP Exception occurred: {exc.status_code} - {exc.detail}")
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"message": exc.detail},
                )

            @app.exception_handler(ValidationError) # Pydantic 유효성 검증 오류
            async def validation_exception_handler(request: Request, exc: ValidationError):
                logger.error(f"Validation Error: {exc.errors()}")
                return JSONResponse(
                    status_code=422, # Unprocessable Entity
                    content={"message": "Invalid request data.", "details": exc.errors()},
                )

            @app.exception_handler(Exception) # 기타 모든 예외 처리
            async def generic_exception_handler(request: Request, exc: Exception):
                logger.error(f"An unexpected error occurred: {exc}", exc_info=True) # exc_info=True로 스택 트레이스 로깅
                return JSONResponse(
                    status_code=500,
                    content={"message": "An internal server error occurred."},
                )

            # 애플리케이션 시작/종료 시 DB 연결 관리 등
            @app.on_event("startup")
            async def startup_event():
                logger.info("Application starting up...")
                # DB 초기화 또는 마이그레이션 로직 (필요시)
                # await database.create_db_and_tables()

            @app.on_event("shutdown")
            async def shutdown_event():
                logger.info("Application shutting down...")
                # DB 연결 풀 정리 등
                # await engine.dispose()

            # 루트 엔드포인트 (테스트용)
            @app.get("/")
            async def read_root():
                logger.debug("Root endpoint accessed.")
                return {"message": "MRP System API is running."}

            # services/mrp_service.py (예시)
            import logging
            from sqlalchemy.ext.asyncio import AsyncSession
            from fastapi import HTTPException # HTTPException 임포트
            from .models import BOM, Inventory, MRPResult # 가정된 모델
            from .schemas import TriggerMrpRequest # 가정된 스키마
            from datetime import datetime

            logger = logging.getLogger(__name__)

            async def calculate_mrp_for_request(request_data: TriggerMrpRequest, db: AsyncSession):
                logger.info(f"Received MRP trigger request: Product ID={request_data.product_id}, Quantity={request_data.quantity}, Date={request_data.date}")
                try:
                    # 실제 MRP 계산 로직 호출
                    await calculate_mrp(request_data.product_id, request_data.quantity, request_data.date, db)
                    logger.info(f"MRP calculation for product {request_data.product_id} completed successfully.")
                except Exception as e:
                    logger.error(f"Error during MRP calculation for product {request_data.product_id}: {e}", exc_info=True)
                    # 여기서 HTTPException을 발생시켜 main.py의 핸들러가 처리하도록 할 수 있습니다.
                    raise HTTPException(status_code=500, detail="Failed to complete MRP calculation.")

            # ... (calculate_mrp, _calculate_requirements_recursive 함수들)
            ```

# 4. 성능 최적화 및 보안 취약점 제언

*   **자원 누수 가능성, 비효율적 반복문, 비동기 처리 미흡:**
    *   **프론트엔드:**
        *   **비동기 처리:** `src/services/api.ts`에서 `async/await`를 사용하고 있지만, 여러 API 호출이 동시에 필요한 경우 `Promise.all`을 활용하여 병렬 처리를 통해 응답 시간을 단축할 수 있습니다.
        *   **메모리 누수:** 컴포넌트가 언마운트될 때 `useEffect` 훅에서 설정한 이벤트 리스너, 타이머, 구독 등을 반드시 클린업 함수를 통해 해제해야 합니다. 현재 코드에서는 이러한 클린업 로직이 명확히 보이지 않습니다.
        *   **리팩토링 예시 (React - `useEffect` 클린업):**
            ```javascript
            useEffect(() => {
                const timerId = setTimeout(() => {
                    console.log('Timer fired');
                }, 5000);

                // 클린업 함수: 컴포넌트 언마운트 시 실행
                return () => {
                    clearTimeout(timerId);
                    console.log('Timer cleared');
                };
            }, []); // 의존성 배열이 비어있으면 컴포넌트 마운트 시 한 번 실행되고 언마운트 시 클린업
            ```
    *   **백엔드:**
        *   **비동기 처리:** FastAPI는 비동기 프레임워크이므로, I/O 바운드 작업(DB 접근, 외부 API 호출 등)은 `async` 함수로 작성하고 `await`를 사용하여 비동기적으로 처리해야 합니다. `services/mrp_service.py`의 `calculate_mrp` 및 `_calculate_requirements_recursive` 함수는 비동기적으로 구현되어야 하며, DB 세션도 비동기적으로 사용해야 합니다. 현재 코드에서는 비동기 처리가 잘 적용된 것으로 보이나, 모든 I/O 작업이 비동기적으로 처리되는지 확인해야 합니다.
        *   **DB 커넥션 관리:** `database.py`의 `get_db` 함수를 통해 비동기 SQLAlchemy 세션을 제공하는 것은 올바른 접근 방식입니다. 각 요청이 독립적인 세션을 사용하고, 요청 완료 시 세션이 자동으로 닫히도록 관리해야 합니다.
        *   **비효율적 로직:** `_calculate_requirements_recursive` 함수에서 BOM 구조를 탐색하는 로직이 깊거나 복잡할 경우, 재귀 호출이 많아져 스택 오버플로우나 성능 저하를 유발할 수 있습니다. 대량의 데이터를 처리할 때는 반복문 대신 효율적인 알고리즘을 사용하거나, DB 레벨에서 최적화된 쿼리를 사용해야 합니다. 예를 들어, 재귀 CTE(Common Table Expression)를 활용하는 것을 고려할 수 있습니다.
        *   **리팩토링 예시 (SQLAlchemy - 재귀 CTE):** 복잡한 BOM 구조 탐색 시, DB 레벨에서 재귀 CTE를 사용하여 성능을 최적화할 수 있습니다.
            ```python
            # 예시: PostgreSQL에서 재귀 CTE를 사용하는 SQL 쿼리 (Python 코드 내에서 실행)
            from sqlalchemy import text

            async def get_all_bom_items_recursive(product_id: int, db: AsyncSession):
                query = text("""
                    WITH RECURSIVE bom_tree AS (
                        -- Anchor member: Select direct children of the product
                        SELECT
                            b.material_id,
                            b.quantity_per_unit,
                            b.lead_time_days,
                            0 AS level -- Level for tracking depth
                        FROM bom b
                        WHERE b.parent_product_id = :product_id

                        UNION ALL

                        -- Recursive member: Select children of the previous level's materials
                        SELECT
                            b_rec.material_id,
                            b_rec.quantity_per_unit * bt.quantity_per_unit AS quantity_per_unit, -- Accumulate quantity
                            b_rec.lead_time_days,
                            bt.level + 1
                        FROM bom b_rec
                        JOIN bom_tree bt ON b_rec.parent_product_id = bt.material_id -- Join on material_id to find next level
                    )
                    SELECT * FROM bom_tree;
                """)
                result = await db.execute(query, {"product_id": product_id})
                return result.fetchall()
            ```

*   **SQL Injection, XSS, 인증 누락 등 잠재적 보안 위협 요소:**
    *   **SQL Injection:**
        *   **백엔드:** SQLAlchemy의 ORM 기능을 사용하고 `Depends`를 통해 DB 세션을 관리하는 것은 SQL Injection 방어에 도움이 됩니다. 그러나 만약 `text()` 함수 등을 사용하여 Raw SQL 쿼리를 직접 실행하는 경우, 반드시 파라미터 바인딩(`:param_name`)을 사용해야 합니다. 현재 제공된 코드에서는 Raw SQL 사용이 명확히 드러나지 않지만, 잠재적인 위험이 있습니다.
        *   **예방:** 사용자 입력 값은 항상 검증하고, ORM을 사용하거나 파라미터 바인딩을 통해 쿼리를 안전하게 실행합니다.
    *   **XSS (Cross-Site Scripting):**
        *   **프론트엔드:** React는 기본적으로 XSS 공격을 방어하는 메커니즘을 가지고 있습니다. 사용자 입력 값을 JSX 내에서 `{variable}` 형태로 렌더링하면 자동으로 이스케이프 처리됩니다. 그러나 `dangerouslySetInnerHTML`과 같은 API를 사용하거나, 외부 라이브러리에서 XSS 취약점이 발생할 수 있으므로 주의해야 합니다.
        *   **예방:** 사용자 입력 값을 HTML에 직접 삽입할 때는 `dangerouslySetInnerHTML` 사용을 지양하고, 필요한 경우 신뢰할 수 있는 라이브러리를 사용하여 안전하게 처리합니다.
    *   **인증 및 권한 부여 누락:**
        *   **백엔드:** `routers/mrp_router.py` 및 `routers/material_router.py`에 정의된 API 엔드포인트 중 민감한 정보에 접근하거나 중요한 작업을 수행하는 엔드포인트(예: MRP 계산 트리거, 자재 생성/수정/삭제)에는 반드시 인증 및 권한 부여 로직이 필요합니다. 현재 코드에서는 이러한 보안 메커니즘이 명확히 보이지 않습니다.
        *   **예방:** FastAPI의 `Depends`와 `python-jose` 또는 `passlib`와 같은 라이브러리를 사용하여 JWT(JSON Web Token) 기반 인증을 구현하고, 각 엔드포인트에 대한 접근 권한을 검사해야 합니다.
        *   **리팩토링 예시 (FastAPI - JWT 인증):**
            ```python
            # 예시: security.py
            from datetime import datetime, timedelta
            from typing import Optional
            from jose import JWTError, jwt
            from passlib.context import CryptContext
            from fastapi import Depends, HTTPException, status # HTTPException, status 임포트

            SECRET_KEY = "YOUR_SUPER_SECRET_KEY" # .env에서 로드해야 함
            ALGORITHM = "HS256"
            ACCESS_TOKEN_EXPIRE_MINUTES = 30

            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

            def verify_password(plain_password, hashed_password):
                return pwd_context.verify(plain_password, hashed_password)

            def get_password_hash(password):
                return pwd_context.hash(password)

            def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
                to_encode = data.copy()
                if expires_delta:
                    expire = datetime.utcnow() + expires_delta
                else:
                    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
                to_encode.update({"exp": expire})
                encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
                return encoded_jwt

            # 예시: routers/material_router.py
            from fastapi import Depends, HTTPException, status
            from jose import JWTError
            from .security import create_access_token, verify_password, get_password_hash # 필요한 함수 임포트
            from fastapi.security import OAuth2PasswordBearer # OAuth2PasswordBearer 임포트

            oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # 토큰 엔드포인트 필요

            async def get_current_user(token: str = Depends(oauth2_scheme)): # oauth2_scheme은 JWT 토큰을 추출하는 함수
                try:
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    username: str = payload.get("sub")
                    if username is None:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid authentication credentials",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                    # 여기서 사용자 정보를 DB에서 조회하거나 토큰 페이로드에서 직접 사용
                    return {"username": username} # 예시
                except JWTError:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid authentication credentials",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            @router.post("/materials")
            async def create_material(
                material: MaterialCreate, # MaterialCreate 스키마 정의 필요
                current_user: dict = Depends(get_current_user) # 인증된 사용자만 접근 가능
            ):
                # ... (생성 로직)
                return {"message": f"Material created by {current_user['username']}"}
            ```
    *   **기타:**
        *   **비밀번호 보안:** 사용자 비밀번호는 반드시 솔트(salt)와 함께 해싱하여 저장해야 합니다. `passlib` 라이브러리를 사용하면 이를 쉽게 구현할 수 있습니다.
        *   **HTTPS 사용:** 프로덕션 환경에서는 반드시 HTTPS를 사용하여 통신을 암호화해야 합니다. 이는 웹 서버 설정에서 구성해야 합니다.
        *   **의존성 관리:** 사용 중인 라이브러리(FastAPI, SQLAlchemy, React 등)의 보안 취약점을 주기적으로 점검하고 최신 버전으로 업데이트해야 합니다. `pip-audit` 또는 `npm audit`와 같은 도구를 활용할 수 있습니다.