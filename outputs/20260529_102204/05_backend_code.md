## 1. 환경 설정 및 데이터베이스 초기화 (Config / Database)

### `.env` 파일 예시

```dotenv
DATABASE_URL=postgresql+asyncpg://user:password@db_host:5432/mrp_db
SECRET_KEY=your_super_secret_key_here
# 추가적인 환경 변수들...
```

### `config.py`

```python
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# .env 파일 로드
load_dotenv()

class Settings(BaseSettings):
    """
    애플리케이션 설정을 관리하는 클래스.
    환경 변수로부터 설정을 로드합니다.
    """
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./sql_app.db") # 기본값으로 SQLite 사용
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_secret_key")
    # 추가적인 환경 변수들을 여기에 정의합니다.

    class Config:
        env_file = ".env"
        extra = "ignore" # .env 파일에 정의되지 않은 환경 변수는 무시

# 설정 객체 인스턴스화
settings = Settings()
```

### `database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from .config import settings

# 비동기 SQLAlchemy 엔진 생성
# DATABASE_URL에 따라 적절한 드라이버를 사용합니다.
# 예: postgresql+asyncpg://user:password@host:port/dbname
# 예: mysql+aiomysql://user:password@host:port/dbname
engine = create_async_engine(
    settings.DATABASE_URL,
    future=True,
    echo=True  # 개발 시 SQL 쿼 로깅 활성화
)

# 비동기 세션 로컬 생성
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# SQLAlchemy 모델의 기본 클래스
Base = declarative_base()

async def get_db():
    """
    데이터베이스 세션을 제공하는 의존성 함수.
    FastAPI의 DI 시스템을 통해 각 요청마다 새로운 세션을 주입합니다.
    """
    async with AsyncSessionLocal() as session:
        yield session

# 데이터베이스 테이블 생성 (필요시)
async def init_db():
    """
    애플리케이션 시작 시 데이터베이스 테이블을 생성합니다.
    """
    async with engine.begin() as conn:
        # Base.metadata.drop_all(bind=engine) # 개발 중 스키마 초기화를 위해 사용 가능
        await conn.run_sync(Base.metadata.create_all)
```

## 2. 데이터 모델 및 스키마 (Models / Schemas)

### `models.py`

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Material(Base):
    """
    자재 정보를 나타내는 데이터베이스 모델.
    """
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    unit = Column(String, nullable=False) # 예: kg, EA, L
    description = Column(String, nullable=True)

    # 관계 설정 (예시)
    bom_items_as_parent = relationship("BOM", back_populates="parent_material", foreign_keys="BOM.parent_material_id")
    bom_items_as_child = relationship("BOM", back_populates="child_material", foreign_keys="BOM.child_material_id")
    inventory_items = relationship("Inventory", back_populates="material")
    mrp_results = relationship("MRPResult", back_populates="material")
    production_plans = relationship("ProductionPlan", back_populates="product_material")

class BOM(Base):
    """
    BOM (Bill of Materials) 정보를 나타내는 데이터베이스 모델.
    제품 또는 반제품을 구성하는 자재들의 계층 구조 및 소요량.
    """
    __tablename__ = "boms"

    id = Column(Integer, primary_key=True, index=True)
    parent_material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    child_material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Float, nullable=False) # 상위 자재 1단위당 필요한 하위 자재 수량
    level = Column(Integer, default=0) # BOM 레벨 (0: 최상위 제품)

    # 관계 설정
    parent_material = relationship("Material", foreign_keys=[parent_material_id], back_populates="bom_items_as_parent")
    child_material = relationship("Material", foreign_keys=[child_material_id], back_populates="bom_items_as_child")

class Inventory(Base):
    """
    각 자재의 현재 재고 정보를 나타내는 데이터베이스 모델.
    """
    __tablename__ = "inventories"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    location = Column(String, nullable=True) # 재고 위치
    last_updated = Column(DateTime, default=datetime.utcnow)

    # 관계 설정
    material = relationship("Material", back_populates="inventory_items")

class ProductionPlan(Base):
    """
    생산 계획 정보를 나타내는 데이터베이스 모델.
    특정 기간 동안 생산할 제품 또는 반제품의 계획.
    """
    __tablename__ = "production_plans"

    id = Column(Integer, primary_key=True, index=True)
    product_material_id = Column(Integer, ForeignKey("materials.id"), nullable=False) # 생산할 제품의 자재 ID
    planned_quantity = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계 설정
    product_material = relationship("Material", back_populates="production_plans")
    mrp_results = relationship("MRPResult", back_populates="production_plan")

class MRPResult(Base):
    """
    MRP 계산 결과를 나타내는 데이터베이스 모델.
    """
    __tablename__ = "mrp_results"

    id = Column(Integer, primary_key=True, index=True)
    production_plan_id = Column(Integer, ForeignKey("production_plans.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    calculation_date = Column(DateTime, default=datetime.utcnow)
    total_requirements = Column(Float, nullable=False) # 총 소요량
    net_requirements = Column(Float, nullable=False) # 순 소요량
    order_proposal_quantity = Column(Float, nullable=False) # 발주 제안 수량
    # 추가적인 MRP 관련 필드 (예: 리드 타임, 안전 재고 고려 여부 등)

    # 관계 설정
    production_plan = relationship("ProductionPlan", back_populates="mrp_results")
    material = relationship("Material", back_populates="mrp_results")
```

### `schemas.py`

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal # 소수점 정밀도 관리를 위해 Decimal 사용 고려

# --- Material Schemas ---
class MaterialBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, example="Steel Plate")
    unit: str = Field(..., min_length=1, max_length=50, example="kg")
    description: Optional[str] = Field(None, max_length=1000, example="High-strength steel plate for chassis")

class MaterialCreate(MaterialBase):
    pass

class MaterialUpdate(MaterialBase):
    # 업데이트 시 일부 필드는 선택 사항으로 처리
    name: Optional[str] = Field(None, min_length=1, max_length=255, example="Steel Plate")
    unit: Optional[str] = Field(None, min_length=1, max_length=50, example="kg")
    description: Optional[str] = Field(None, max_length=1000, example="High-strength steel plate for chassis")

class MaterialRead(MaterialBase):
    id: int

    class Config:
        orm_mode = True # SQLAlchemy 모델을 Pydantic 모델로 변환할 때 사용

# --- BOM Schemas ---
class BOMBase(BaseModel):
    parent_material_id: int = Field(..., gt=0, example=1)
    child_material_id: int = Field(..., gt=0, example=2)
    quantity: float = Field(..., gt=0, example=2.5) # 상위 자재 1단위당 필요한 하위 자재 수량
    level: int = Field(0, ge=0, example=1)

    @validator('quantity')
    def quantity_must_be_positive(cls, value):
        if value <= 0:
            raise ValueError('Quantity must be positive')
        return value

class BOMCreate(BOMBase):
    pass

class BOMUpdate(BOMBase):
    parent_material_id: Optional[int] = Field(None, gt=0, example=1)
    child_material_id: Optional[int] = Field(None, gt=0, example=2)
    quantity: Optional[float] = Field(None, gt=0, example=2.5)
    level: Optional[int] = Field(None, ge=0, example=1)

class BOMRead(BOMBase):
    id: int
    parent_material: Optional[MaterialRead] = None # 중첩된 Material 정보 (조회 시)
    child_material: Optional[MaterialRead] = None # 중첩된 Material 정보 (조회 시)

    class Config:
        orm_mode = True

# --- Inventory Schemas ---
class InventoryBase(BaseModel):
    material_id: int = Field(..., gt=0, example=1)
    quantity: float = Field(..., ge=0, example=1000.5)
    location: Optional[str] = Field(None, max_length=255, example="Warehouse A, Shelf 3")

    @validator('quantity')
    def quantity_must_be_non_negative(cls, value):
        if value < 0:
            raise ValueError('Quantity cannot be negative')
        return value

class InventoryCreate(InventoryBase):
    pass

class InventoryUpdate(InventoryBase):
    material_id: Optional[int] = Field(None, gt=0, example=1)
    quantity: Optional[float] = Field(None, ge=0, example=1000.5)
    location: Optional[str] = Field(None, max_length=255, example="Warehouse A, Shelf 3")

class InventoryRead(InventoryBase):
    id: int
    material: Optional[MaterialRead] = None # 중첩된 Material 정보 (조회 시)
    last_updated: datetime

    class Config:
        orm_mode = True

# --- ProductionPlan Schemas ---
class ProductionPlanBase(BaseModel):
    product_material_id: int = Field(..., gt=0, example=1)
    planned_quantity: float = Field(..., gt=0, example=500.0)
    start_date: datetime
    end_date: datetime = Field(..., example="2023-12-31T23:59:59")

    @validator('end_date')
    def end_date_must_be_after_start_date(cls, value, values):
        start_date = values.get('start_date')
        if start_date and value <= start_date:
            raise ValueError('End date must be after start date')
        return value

class ProductionPlanCreate(ProductionPlanBase):
    pass

class ProductionPlanUpdate(ProductionPlanBase):
    product_material_id: Optional[int] = Field(None, gt=0, example=1)
    planned_quantity: Optional[float] = Field(None, gt=0, example=500.0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class ProductionPlanRead(ProductionPlanBase):
    id: int
    product_material: Optional[MaterialRead] = None # 중첩된 Material 정보 (조회 시)
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# --- MRPResult Schemas ---
class MRPResultBase(BaseModel):
    production_plan_id: int = Field(..., gt=0, example=1)
    material_id: int = Field(..., gt=0, example=2)
    total_requirements: float = Field(..., ge=0, example=1250.0)
    net_requirements: float = Field(..., ge=0, example=1000.0)
    order_proposal_quantity: float = Field(..., ge=0, example=1000.0)

    @validator('total_requirements', 'net_requirements', 'order_proposal_quantity')
    def quantities_must_be_non_negative(cls, value):
        if value < 0:
            raise ValueError('Quantity cannot be negative')
        return value

class MRPResultCreate(MRPResultBase):
    pass

class MRPResultRead(MRPResultBase):
    id: int
    calculation_date: datetime
    production_plan: Optional[ProductionPlanRead] = None # 중첩된 ProductionPlan 정보 (조회 시)
    material: Optional[MaterialRead] = None # 중첩된 Material 정보 (조회 시)

    class Config:
        orm_mode = True

# --- MRP Calculation Trigger Schema ---
class MRPCalculateTrigger(BaseModel):
    production_plan_id: int = Field(..., gt=0, example=1)

# --- Dashboard Data Schema ---
class DashboardMRPData(BaseModel):
    material_id: int
    material_name: str
    total_shortage: float = Field(..., ge=0, example=500.0) # 총 부족량
    total_order_proposal: float = Field(..., ge=0, example=1500.0) # 총 발주 제안

class DashboardSummary(BaseModel):
    total_materials_to_order: int = Field(..., ge=0, example=10)
    total_value_of_orders: float = Field(..., ge=0, example=15000.0)
    upcoming_deadlines: List[str] = Field(..., example=["2023-12-15", "2023-12-20"])

class MRPDashboardResponse(BaseModel):
    summary: DashboardSummary
    material_breakdown: List[DashboardMRPData]
```

## 3. 비즈니스 로직 및 API 엔드포인트 (Services / Routers)

### `services/material_service.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from .. import models, schemas
from ..exceptions import NotFoundException, DuplicateEntryException

class MaterialService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_material(self, material: schemas.MaterialCreate) -> schemas.MaterialRead:
        """새로운 자재를 생성합니다."""
        # 중복 이름 체크
        existing_material = await self.db.execute(
            select(models.Material).filter(models.Material.name == material.name)
        )
        if existing_material.scalars().first():
            raise DuplicateEntryException(f"Material with name '{material.name}' already exists.")

        db_material = models.Material(**material.model_dump())
        self.db.add(db_material)
        await self.db.commit()
        await self.db.refresh(db_material)
        return schemas.MaterialRead.from_orm(db_material)

    async def get_materials(self, skip: int = 0, limit: int = 100) -> List[schemas.MaterialRead]:
        """모든 자재 목록을 조회합니다."""
        stmt = select(models.Material).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        materials = result.scalars().all()
        return [schemas.MaterialRead.from_orm(mat) for mat in materials]

    async def get_material(self, material_id: int) -> schemas.MaterialRead:
        """특정 자재 상세 정보를 조회합니다."""
        stmt = select(models.Material).filter(models.Material.id == material_id)
        # 필요한 경우 관계 로딩 추가 (예: BOM 정보)
        # stmt = stmt.options(selectinload(models.Material.bom_items_as_parent))
        result = await self.db.execute(stmt)
        db_material = result.scalars().first()
        if not db_material:
            raise NotFoundException(f"Material with id {material_id} not found.")
        return schemas.MaterialRead.from_orm(db_material)

    async def update_material(self, material_id: int, material_update: schemas.MaterialUpdate) -> schemas.MaterialRead:
        """특정 자재 정보를 업데이트합니다."""
        stmt = select(models.Material).filter(models.Material.id == material_id)
        result = await self.db.execute(stmt)
        db_material = result.scalars().first()
        if not db_material:
            raise NotFoundException(f"Material with id {material_id} not found.")

        # 이름 변경 시 중복 체크
        if material_update.name is not None and db_material.name != material_update.name:
            existing_material = await self.db.execute(
                select(models.Material).filter(models.Material.name == material_update.name)
            )
            if existing_material.scalars().first():
                raise DuplicateEntryException(f"Material with name '{material_update.name}' already exists.")

        # Pydantic 모델의 exclude_unset=True를 사용하여 값이 설정된 필드만 업데이트
        update_data = material_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_material, field, value)

        await self.db.commit()
        await self.db.refresh(db_material)
        return schemas.MaterialRead.from_orm(db_material)

    async def delete_material(self, material_id: int) -> None:
        """특정 자재를 삭제합니다."""
        stmt = select(models.Material).filter(models.Material.id == material_id)
        result = await self.db.execute(stmt)
        db_material = result.scalars().first()
        if not db_material:
            raise NotFoundException(f"Material with id {material_id} not found.")

        # 관련 데이터 존재 시 삭제 방지 (예: BOM, Inventory, MRPResult, ProductionPlan 등)
        # cascade delete를 사용하지 않는 경우, 명시적으로 관련 데이터를 확인하고 삭제하거나 오류를 발생시켜야 합니다.
        # 예:
        # bom_check_parent = await self.db.execute(select(models.BOM).filter(models.BOM.parent_material_id == material_id).limit(1))
        # bom_check_child = await self.db.execute(select(models.BOM).filter(models.BOM.child_material_id == material_id).limit(1))
        # inventory_check = await self.db.execute(select(models.Inventory).filter(models.Inventory.material_id == material_id).limit(1))
        # mrp_check = await self.db.execute(select(models.MRPResult).filter(models.MRPResult.material_id == material_id).limit(1))
        # production_plan_check = await self.db.execute(select(models.ProductionPlan).filter(models.ProductionPlan.product_material_id == material_id).limit(1))

        # if bom_check_parent.scalars().first() or bom_check_child.scalars().first() or \
        #    inventory_check.scalars().first() or mrp_check.scalars().first() or \
        #    production_plan_check.scalars().first():
        #     raise BadRequestException("Cannot delete material with associated BOM, Inventory, MRP results, or Production Plans.")

        await self.db.delete(db_material)
        await self.db.commit()
```

### `services/mrp_service.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, aliased
from sqlalchemy import func
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

from .. import models, schemas
from ..exceptions import NotFoundException, BadRequestException

class MRPService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_material_details(self, material_id: int) -> models.Material:
        """자재 상세 정보를 조회합니다."""
        stmt = select(models.Material).filter(models.Material.id == material_id)
        result = await self.db.execute(stmt)
        material = result.scalars().first()
        if not material:
            raise NotFoundException(f"Material with id {material_id} not found.")
        return material

    async def _get_bom_children_with_details(self, parent_material_id: int) -> List[Tuple[models.BOM, models.Material]]:
        """
        특정 자재의 직접적인 하위 BOM 항목들과 해당 하위 자재 정보를 함께 조회합니다.
        """
        stmt = select(models.BOM, models.Material).join(models.Material, models.BOM.child_material_id == models.Material.id)\
               .filter(models.BOM.parent_material_id == parent_material_id)
        result = await self.db.execute(stmt)
        return result.all()

    async def _get_inventory_quantity(self, material_id: int) -> float:
        """특정 자재의 현재 재고량을 조회합니다."""
        stmt = select(models.Inventory.quantity).filter(models.Inventory.material_id == material_id)
        result = await self.db.execute(stmt)
        inventory_item = result.scalars().first()
        return inventory_item if inventory_item is not None else 0.0

    async def _calculate_requirements_recursive(
        self,
        material_id: int,
        demand_quantity: float,
        calculation_date: datetime,
        results: Dict[int, Dict[str, Any]], # {material_id: {total_req, net_req, order_prop, material_name, material_unit}}
        production_plan_id: int,
        level: int = 0 # 재귀 깊이 추적
    ):
        """
        재귀적으로 BOM을 탐색하며 자재 소요량을 계산합니다.
        """
        material = await self._get_material_details(material_id)
        inventory_qty = await self._get_inventory_quantity(material_id)

        # 현재 자재의 총 소요량 업데이트
        if material_id not in results:
            results[material_id] = {
                "total_requirements": 0.0,
                "net_requirements": 0.0,
                "order_proposal_quantity": 0.0,
                "material_name": material.name,
                "material_unit": material.unit
            }

        results[material_id]["total_requirements"] += demand_quantity

        # 순 소요량 계산 (총 소요량 - 현재 재고)
        net_req = max(0.0, results[material_id]["total_requirements"] - inventory_qty)
        results[material_id]["net_requirements"] = net_req

        # 발주 제안 수량 계산 (순 소요량이 0보다 크면 발주 제안)
        # TODO: 리드 타임, 안전 재고, 배치 크기 등 복잡한 로직 추가 필요
        if net_req > 0:
            results[material_id]["order_proposal_quantity"] = net_req # 단순화된 로직

        # 하위 BOM 항목에 대한 소요량 계산
        bom_children_with_details = await self._get_bom_children_with_details(material_id)
        for bom_item, child_material in bom_children_with_details:
            child_material_id = bom_item.child_material_id
            # 상위 자재 1단위당 필요한 하위 자재 수량 * 현재 단계의 총 소요량
            child_quantity_needed = bom_item.quantity * demand_quantity
            await self._calculate_requirements_recursive(
                child_material_id,
                child_quantity_needed,
                calculation_date,
                results,
                production_plan_id,
                level + 1
            )

    async def calculate_mrp(self, trigger: schemas.MRPCalculateTrigger) -> List[schemas.MRPResultRead]:
        """
        주어진 생산 계획에 대해 MRP 계산을 수행하고 결과를 저장합니다.
        """
        # 1. 생산 계획 조회
        plan_stmt = select(models.ProductionPlan).filter(models.ProductionPlan.id == trigger.production_plan_id)
        plan_result = await self.db.execute(plan_stmt)
        production_plan = plan_result.scalars().first()
        if not production_plan:
            raise NotFoundException(f"Production plan with id {trigger.production_plan_id} not found.")

        # 2. MRP 계산 초기화
        calculation_date = datetime.utcnow()
        mrp_results_dict: Dict[int, Dict[str, Any]] = {} # {material_id: {total_req, net_req, order_prop, material_name, material_unit}}

        # 3. 최상위 제품에 대한 소요량 계산 시작
        await self._calculate_requirements_recursive(
            material_id=production_plan.product_material_id,
            demand_quantity=production_plan.planned_quantity,
            calculation_date=calculation_date,
            results=mrp_results_dict,
            production_plan_id=production_plan.id
        )

        # 4. 기존 MRP 결과 삭제 (동일 생산 계획에 대한 가장 최근 결과)
        # 동일한 production_plan_id에 대해 가장 최근 calculation_date를 가진 결과들을 삭제합니다.
        # 이는 MRP 재계산 시 이전 결과가 중복 저장되는 것을 방지합니다.
        delete_stmt = select(models.MRPResult).filter(
            models.MRPResult.production_plan_id == production_plan.id,
            models.MRPResult.calculation_date == calculation_date # 동일 계산 시점의 결과만 삭제
        )
        existing_results = await self.db.execute(delete_stmt)
        for res in existing_results.scalars().all():
            await self.db.delete(res)
        await self.db.commit() # 삭제 후 커밋

        # 5. MRP 결과 저장
        saved_results: List[models.MRPResult] = []
        for material_id, data in mrp_results_dict.items():
            db_mrp_result = models.MRPResult(
                production_plan_id=production_plan.id,
                material_id=material_id,
                calculation_date=calculation_date,
                total_requirements=data["total_requirements"],
                net_requirements=data["net_requirements"],
                order_proposal_quantity=data["order_proposal_quantity"]
            )
            self.db.add(db_mrp_result)
            saved_results.append(db_mrp_result)

        await self.db.commit()

        # 6. 저장된 결과 Pydantic 스키마로 변환하여 반환
        # 관계 로딩을 위해 다시 조회하거나, 저장 시 관계 객체를 함께 관리해야 함
        response_schemas: List[schemas.MRPResultRead] = []
        for saved_res in saved_results:
            # Material 및 ProductionPlan 정보를 조회하여 중첩 스키마 생성
            material_detail = await self._get_material_details(saved_res.material_id)
            plan_detail = await self.db.get(models.ProductionPlan, saved_res.production_plan_id) # get 사용

            response_schemas.append(
                schemas.MRPResultRead(
                    id=saved_res.id,
                    production_plan_id=saved_res.production_plan_id,
                    material_id=saved_res.material_id,
                    calculation_date=saved_res.calculation_date,
                    total_requirements=saved_res.total_requirements,
                    net_requirements=saved_res.net_requirements,
                    order_proposal_quantity=saved_res.order_proposal_quantity,
                    production_plan=schemas.ProductionPlanRead.from_orm(plan_detail),
                    material=schemas.MaterialRead.from_orm(material_detail)
                )
            )
        return response_schemas

    async def get_mrp_results(
        self,
        production_plan_id: Optional[int] = None,
        material_id: Optional[int] = None,
        calculation_date: Optional[datetime] = None, # 특정 계산 시점 결과 조회
        skip: int = 0,
        limit: int = 100
    ) -> List[schemas.MRPResultRead]:
        """MRP 계산 결과를 조회합니다."""
        stmt = select(models.MRPResult)
        if production_plan_id:
            stmt = stmt.filter(models.MRPResult.production_plan_id == production_plan_id)
        if material_id:
            stmt = stmt.filter(models.MRPResult.material_id == material_id)
        if calculation_date:
            stmt = stmt.filter(models.MRPResult.calculation_date == calculation_date)

        # 관계 로딩을 통해 한 번의 쿼리로 데이터 가져오기
        stmt = stmt.options(
            selectinload(models.MRPResult.production_plan).joinedload(models.ProductionPlan.product_material),
            selectinload(models.MRPResult.material)
        )

        result = await self.db.execute(stmt.offset(skip).limit(limit))
        mrp_results = result.scalars().all()

        return [schemas.MRPResultRead.from_orm(res) for res in mrp_results]

    async def get_dashboard_data(self) -> schemas.MRPDashboardResponse:
        """미니 대시보드에 필요한 집계 데이터를 조회합니다."""
        # 가장 최근의 MRP 계산 결과들을 기준으로 집계
        latest_calculation_date_stmt = select(func.max(models.MRPResult.calculation_date))
        latest_calculation_date_result = await self.db.execute(latest_calculation_date_stmt)
        latest_calculation_date = latest_calculation_date_result.scalar()

        if not latest_calculation_date:
            return schemas.MRPDashboardResponse(
                summary=schemas.DashboardSummary(
                    total_materials_to_order=0,
                    total_value_of_orders=0.0,
                    upcoming_deadlines=[]
                ),
                material_breakdown=[]
            )

        # 자재별 총 부족량 및 발주 제안량 집계
        material_breakdown_stmt = select(
            models.MRPResult.material_id,
            models.Material.name,
            func.sum(models.MRPResult.net_requirements).label("total_shortage"),
            func.sum(models.MRPResult.order_proposal_quantity).label("total_order_proposal")
        ).join(models.Material, models.MRPResult.material_id == models.Material.id)\
         .filter(models.MRPResult.calculation_date == latest_calculation_date)\
         .group_by(models.MRPResult.material_id, models.Material.name)\
         .order_by(func.sum(models.MRPResult.order_proposal_quantity).desc())

        material_breakdown_result = await self.db.execute(material_breakdown_stmt)
        material_breakdown_data = material_breakdown_result.fetchall()

        dashboard_material_breakdown: List[schemas.DashboardMRPData] = []
        total_materials_to_order = 0
        total_value_of_orders = 0.0

        for row in material_breakdown_data:
            material_id, material_name, total_shortage, total_order_proposal = row
            dashboard_material_breakdown.append(
                schemas.DashboardMRPData(
                    material_id=material_id,
                    material_name=material_name,
                    total_shortage=round(total_shortage, 2),
                    total_order_proposal=round(total_order_proposal, 2)
                )
            )
            if total_order_proposal > 0:
                total_materials_to_order += 1
                total_value_of_orders += total_order_proposal # TODO: 실제 단가 적용 필요

        # 예정된 마감일 조회 (가장 가까운 5개)
        upcoming_deadlines_stmt = select(models.ProductionPlan.end_date)\
            .filter(models.ProductionPlan.end_date >= datetime.utcnow())\
            .order_by(models.ProductionPlan.end_date)\
            .limit(5)
        upcoming_deadlines_result = await self.db.execute(upcoming_deadlines_stmt)
        upcoming_deadlines = [
            date.strftime("%Y-%m-%d") for date in upcoming_deadlines_result.scalars().all()
        ]

        summary = schemas.DashboardSummary(
            total_materials_to_order=total_materials_to_order,
            total_value_of_orders=round(total_value_of_orders, 2),
            upcoming_deadlines=upcoming_deadlines
        )

        return schemas.MRPDashboardResponse(
            summary=summary,
            material_breakdown=dashboard_material_breakdown
        )
```

### `routers/material_router.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from .. import schemas, services
from ..database import get_db
from ..exceptions import NotFoundException, DuplicateEntryException, BadRequestException

router = APIRouter(
    prefix="/materials",
    tags=["Materials"],
    responses={404: {"description": "Not found"}}
)

# 의존성 주입을 위한 함수
async def get_material_service(db: AsyncSession = Depends(get_db)) -> services.MaterialService:
    return services.MaterialService(db)

@router.post("/", response_model=schemas.MaterialRead, status_code=status.HTTP_201_CREATED)
async def create_material(
    material: schemas.MaterialCreate,
    material_service: services.MaterialService = Depends(get_material_service)
):
    """
    새로운 자재를 생성합니다.
    """
    try:
        return await material_service.create_material(material)
    except DuplicateEntryException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/", response_model=List[schemas.MaterialRead])
async def read_materials(
    skip: int = 0,
    limit: int = 100,
    material_service: services.MaterialService = Depends(get_material_service)
):
    """
    모든 자재 목록을 조회합니다.
    """
    try:
        return await material_service.get_materials(skip=skip, limit=limit)
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/{material_id}", response_model=schemas.MaterialRead)
async def read_material(
    material_id: int,
    material_service: services.MaterialService = Depends(get_material_service)
):
    """
    특정 자재 상세 정보를 조회합니다.
    """
    try:
        return await material_service.get_material(material_id=material_id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.put("/{material_id}", response_model=schemas.MaterialRead)
async def update_material(
    material_id: int,
    material_update: schemas.MaterialUpdate,
    material_service: services.MaterialService = Depends(get_material_service)
):
    """
    특정 자재 정보를 업데이트합니다.
    """
    try:
        return await material_service.update_material(material_id=material_id, material_update=material_update)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateEntryException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: int,
    material_service: services.MaterialService = Depends(get_material_service)
):
    """
    특정 자재를 삭제합니다.
    """
    try:
        await material_service.delete_material(material_id=material_id)
        return # 204 No Content 응답
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")
```

### `routers/mrp_router.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from .. import schemas, services
from ..database import get_db
from ..exceptions import NotFoundException, BadRequestException

router = APIRouter(
    prefix="/mrp",
    tags=["MRP"],
    responses={404: {"description": "Not found"}}
)

# 의존성 주입을 위한 함수
async def get_mrp_service(db: AsyncSession = Depends(get_db)) -> services.MRPService:
    return services.MRPService(db)

@router.post("/calculate", response_model=List[schemas.MRPResultRead], status_code=status.HTTP_201_CREATED)
async def trigger_mrp_calculation(
    trigger: schemas.MRPCalculateTrigger,
    mrp_service: services.MRPService = Depends(get_mrp_service)
):
    """
    MRP 계산을 트리거합니다.
    """
    try:
        return await mrp_service.calculate_mrp(trigger)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/results", response_model=List[schemas.MRPResultRead])
async def get_mrp_results(
    production_plan_id: Optional[int] = None,
    material_id: Optional[int] = None,
    calculation_date_str: Optional[str] = None, # 날짜 문자열로 입력받음
    skip: int = 0,
    limit: int = 100,
    mrp_service: services.MRPService = Depends(get_mrp_service)
):
    """
    MRP 계산 결과를 조회합니다.
    production_plan_id, material_id, 또는 calculation_date로 필터링할 수 있습니다.
    """
    calculation_date: Optional[datetime] = None
    if calculation_date_str:
        try:
            # ISO 8601 형식 (YYYY-MM-DDTHH:MM:SS) 또는 YYYY-MM-DD 형식 파싱
            calculation_date = datetime.fromisoformat(calculation_date_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format for calculation_date. Use ISO 8601 format (e.g., YYYY-MM-DDTHH:MM:SS).")

    try:
        return await mrp_service.get_mrp_results(
            production_plan_id=production_plan_id,
            material_id=material_id,
            calculation_date=calculation_date,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")

@router.get("/dashboard-data", response_model=schemas.MRPDashboardResponse)
async def get_dashboard_data(
    mrp_service: services.MRPService = Depends(get_mrp_service)
):
    """
    미니 대시보드에 필요한 집계 데이터를 조회합니다.
    """
    try:
        return await mrp_service.get_dashboard_data()
    except Exception as e:
        # 로깅 추가
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")
```

### `main.py` (FastAPI 애플리케이션 진입점)

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError # SQLAlchemy 관련 예외 처리

from .config import settings
from .database import engine, init_db
from .routers import material_router, mrp_router
from .exceptions import NotFoundException, DuplicateEntryException, BadRequestException # 사용자 정의 예외 임포트

# FastAPI 애플리케이션 인스턴스 생성
app = FastAPI(
    title="MRP System API",
    description="API for Material Requirements Planning system.",
    version="1.0.0",
    contact={
        "name": "MRP System Support",
        "url": "http://example.com/support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# 라우터 등록
app.include_router(material_router.router)
app.include_router(mrp_router.router)

# --- 전역 예외 처리 ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic 유효성 검증 오류에 대한 사용자 정의 응답.
    """
    # 에러 메시지를 좀 더 사용자 친화적으로 가공
    error_details = []
    for error in exc.errors():
        field = ".".join(map(str, error["loc"]))
        msg = error["msg"]
        error_details.append(f"Field '{field}': {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": error_details, "message": "Input validation error"},
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    FastAPI의 기본 HTTPException에 대한 사용자 정의 응답.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "message": f"HTTP error: {exc.status_code}"},
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """
    SQLAlchemy 관련 예외에 대한 사용자 정의 응답.
    """
    # 로깅 추가: 실제 운영 환경에서는 로깅 라이브러리 사용
    print(f"SQLAlchemy Error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred.", "message": "Internal Server Error"},
    )

# 사용자 정의 예외 핸들러 등록 (exceptions.py에 정의된 예외 사용)
@app.exception_handler(NotFoundException)
async def not_found_exception_handler(request: Request, exc: NotFoundException):
    return JSONResponse(
        status_code=exc.status_code, # HTTPException에서 상속받으므로 status_code 사용 가능
        content={"detail": exc.detail, "message": "Resource not found"},
    )

@app.exception_handler(DuplicateEntryException)
async def duplicate_entry_exception_handler(request: Request, exc: DuplicateEntryException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "message": "Duplicate entry"},
    )

@app.exception_handler(BadRequestException)
async def bad_request_exception_handler(request: Request, exc: BadRequestException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "message": "Bad request"},
    )


# --- 애플리케이션 시작 시 실행되는 코드 ---

@app.on_event("startup")
async def startup_event():
    """
    애플리케이션 시작 시 데이터베이스 테이블 생성 등을 수행합니다.
    """
    try:
        await init_db()
        print("Database tables initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # 운영 환경에서는 이 경우 애플리케이션 시작을 중단하거나 알림을 보낼 수 있습니다.
    print("Application startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    """
    애플리케이션 종료 시 데이터베이스 연결 풀 정리 등을 수행합니다.
    """
    # SQLAlchemy 엔진의 연결 풀을 닫습니다.
    await engine.dispose()
    print("Application shutdown complete.")

# --- 루트 엔드포인트 ---

@app.get("/")
async def read_root():
    """
    API 루트 엔드포인트.
    """
    return {"message": "Welcome to the MRP System API!"}

```

### `exceptions.py`

```python
from fastapi import HTTPException, status

class NotFoundException(HTTPException):
    """찾을 수 없는 리소스에 대한 사용자 정의 예외."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=message)

class DuplicateEntryException(HTTPException):
    """중복된 항목에 대한 사용자 정의 예외."""
    def __init__(self, message: str = "Duplicate entry"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=message)

class BadRequestException(HTTPException):
    """잘못된 요청에 대한 사용자 정의 예외."""
    def __init__(self, message: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
```