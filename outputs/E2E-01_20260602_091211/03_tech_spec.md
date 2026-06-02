```yaml
project_type: python
```

# 1. 오늘 구현할 컴포넌트 및 파일 트리

```
/project-root
├── backend
│   ├── __init__.py
│   ├── main.py
│   ├── api
│   │   ├── __init__.py
│   │   ├── v1
│   │   │   ├── __init__.py
│   │   │   ├── users.py
│   │   │   ├── products.py
│   │   │   └── materials.py
│   │   └── dependencies.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── security.py
│   ├── crud
│   │   ├── __init__.py
│   │   ├── crud_user.py
│   │   ├── crud_product.py
│   │   └── crud_material.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── product.py
│   │   └── material.py
│   ├── schemas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── product.py
│   │   └── material.py
│   ├── tests
│   │   ├── __init__.py
│   │   └── test_api.py
│   └── requirements.txt
├── frontend
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── components
│   │   │   ├── UserList.vue
│   │   │   ├── ProductList.vue
│   │   │   └── MaterialList.vue
│   │   ├── services
│   │   │   ├── api.ts
│   │   │   ├── userService.ts
│   │   │   ├── productService.ts
│   │   │   └── materialService.ts
│   │   └── styles
│   │       └── main.css
│   └── package.json
└── .env
```

# 2. API 엔드포인트 명세 (오늘 구현 범위 한정)

| 경로 (Path)                 | HTTP 메소드 | 설명                               | 요청 (Request Body) Schema (JSON) | 응답 (Response Body) Schema (JSON) |
| :-------------------------- | :---------- | :--------------------------------- | :-------------------------------- | :--------------------------------- |
| `/users`                    | `POST`      | 사용자 생성                        | `{"username": "string", "email": "string", "password": "string", "role": "string"}` | `{"user_id": "integer", "username": "string", "email": "string", "role": "string"}` |
| `/users/{user_id}`          | `GET`       | 특정 사용자 조회                   | -                                 | `{"user_id": "integer", "username": "string", "email": "string", "role": "string"}` |
| `/users`                    | `GET`       | 모든 사용자 조회                   | -                                 | `[{"user_id": "integer", "username": "string", "email": "string", "role": "string"}]` |
| `/products`                 | `POST`      | 제품 생성                          | `{"product_code": "string", "product_name": "string", "unit_of_measure": "string"}` | `{"product_id": "integer", "product_code": "string", "product_name": "string", "unit_of_measure": "string"}` |
| `/products/{product_id}`    | `GET`       | 특정 제품 조회                     | -                                 | `{"product_id": "integer", "product_code": "string", "product_name": "string", "unit_of_measure": "string"}` |
| `/products`                 | `GET`       | 모든 제품 조회                     | -                                 | `[{"product_id": "integer", "product_code": "string", "product_name": "string", "unit_of_measure": "string"}]` |
| `/materials`                | `POST`      | 원자재 생성                        | `{"material_code": "string", "material_name": "string", "unit_of_measure": "string"}` | `{"material_id": "integer", "material_code": "string", "material_name": "string", "unit_of_measure": "string"}` |
| `/materials/{material_id}`  | `GET`       | 특정 원자재 조회                   | -                                 | `{"material_id": "integer", "material_code": "string", "material_name": "string", "unit_of_measure": "string"}` |
| `/materials`                | `GET`       | 모든 원자재 조회                   | -                                 | `[{"material_id": "integer", "material_code": "string", "material_name": "string", "unit_of_measure": "string"}]` |

# 3. 개발 제약사항 및 비즈니스 로직 팁

*   **환경 변수 사용:** 모든 API 키, 데이터베이스 연결 정보, 비밀 키 등은 `.env` 파일에서 로드하여 사용합니다. `backend/core/config.py`에서 환경 변수를 파싱하고 접근합니다.
*   **데이터 유효성 검증:** Pydantic 스키마를 사용하여 API 요청 및 응답 데이터의 유효성을 엄격하게 검증합니다.
*   **인증 및 권한:** 사용자 역할(`role`) 기반의 기본적인 인증 및 권한 부여 로직을 구현합니다. (예: 관리자만 특정 API 접근 가능)
*   **Frontend API 통신:** `frontend/src/services/api.ts`에 정의된 `axios` 인스턴스를 사용하여 모든 API 요청을 처리합니다. 기본 URL은 환경 변수에서 설정합니다.
*   **Frontend 컴포넌트 재사용성:** 공통 UI 요소는 `frontend/src/components` 디렉토리에 분리하여 재사용성을 높입니다.
*   **데이터베이스 모델:** `backend/models` 디렉토리에 SQLAlchemy 모델을 정의하며, `backend/schemas` 디렉토리에는 Pydantic 모델을 정의하여 API 데이터 형식을 관리합니다.
*   **CRUD 함수:** `backend/crud` 디렉토리에 각 모델에 대한 데이터베이스 CRUD(Create, Read, Update, Delete) 함수를 구현합니다.

# [필수 파일 출력 표준 (XML Format)]

<file path="backend/requirements.txt">
fastapi==0.104.1
uvicorn[standard]==0.24.0.post1
sqlalchemy2-stubs==0.0.3
pydantic==2.5.3
python-dotenv==1.0.0
pytest==7.4.3
httpx==0.25.2
SQLAlchemy==2.0.23
</file>

<file path="backend/main.py">
import uvicorn
from fastapi import FastAPI
from backend.api.v1 import users, products, materials
from backend.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(products.router, prefix=settings.API_V1_STR)
app.include_router(materials.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to the Manufacturing Management Simulator API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
</file>

<file path="backend/core/config.py">
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Manufacturing Management Simulator"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key") # In production, use a strong, unique key
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db") # Example for SQLite

    # Add other settings as needed, e.g., email settings, external API keys

settings = Settings()
</file>

<file path="backend/api/v1/users.py">
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.schemas.user import UserCreate, User
from backend.crud import crud_user
from backend.api.dependencies import get_db

router = APIRouter()

@router.post("/users/", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud_user.create_user(db=db, user=user)

@router.get("/users/{user_id}", response_model=User)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud_user.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@router.get("/users/", response_model=list[User])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users
</file>

<file path="backend/api/v1/products.py">
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.schemas.product import ProductCreate, Product
from backend.crud import crud_product
from backend.api.dependencies import get_db

router = APIRouter()

@router.post("/products/", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = crud_product.get_product_by_code(db, product_code=product.product_code)
    if db_product:
        raise HTTPException(status_code=400, detail="Product code already registered")
    return crud_product.create_product(db=db, product=product)

@router.get("/products/{product_id}", response_model=Product)
def read_product(product_id: int, db: Session = Depends(get_db)):
    db_product = crud_product.get_product(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@router.get("/products/", response_model=list[Product])
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = crud_product.get_products(db, skip=skip, limit=limit)
    return products
</file>

<file path="backend/api/v1/materials.py">
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.schemas.material import MaterialCreate, Material
from backend.crud import crud_material
from backend.api.dependencies import get_db

router = APIRouter()

@router.post("/materials/", response_model=Material, status_code=status.HTTP_201_CREATED)
def create_material(material: MaterialCreate, db: Session = Depends(get_db)):
    db_material = crud_material.get_material_by_code(db, material_code=material.material_code)
    if db_material:
        raise HTTPException(status_code=400, detail="Material code already registered")
    return crud_material.create_material(db=db, material=material)

@router.get("/materials/{material_id}", response_model=Material)
def read_material(material_id: int, db: Session = Depends(get_db)):
    db_material = crud_material.get_material(db, material_id=material_id)
    if db_material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return db_material

@router.get("/materials/", response_model=list[Material])
def read_materials(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    materials = crud_material.get_materials(db, skip=skip, limit=limit)
    return materials
</file>

<file path="backend/api/dependencies.py">
from typing import Generator
from backend.database import SessionLocal # Assuming you have a database setup in backend/database.py

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
</file>

<file path="backend/schemas/user.py">
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str # e.g., "admin", "planner", "viewer"

class UserCreate(UserBase):
    password: str

class User(UserBase):
    user_id: int

    class Config:
        from_attributes = True # For SQLAlchemy models
</file>

<file path="backend/schemas/product.py">
from pydantic import BaseModel

class ProductBase(BaseModel):
    product_code: str
    product_name: str
    unit_of_measure: str

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    product_id: int

    class Config:
        from_attributes = True
</file>

<file path="backend/schemas/material.py">
from pydantic import BaseModel

class MaterialBase(BaseModel):
    material_code: str
    material_name: str
    unit_of_measure: str

class MaterialCreate(MaterialBase):
    pass

class Material(MaterialBase):
    material_id: int

    class Config:
        from_attributes = True
</file>

<file path="backend/crud/crud_user.py">
from sqlalchemy.orm import Session
from backend.models.user import User as UserModel # Assuming User model is in backend/models/user.py
from backend.schemas.user import UserCreate
from backend.core.security import get_password_hash # Assuming password hashing utility

def get_user(db: Session, user_id: int):
    return db.query(UserModel).filter(UserModel.user_id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(UserModel).filter(UserModel.email == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(UserModel).offset(skip).limit(limit).all()

def create_user(db: Session, user: UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = UserModel(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
</file>

<file path="backend/crud/crud_product.py">
from sqlalchemy.orm import Session
from backend.models.product import Product as ProductModel
from backend.schemas.product import ProductCreate

def get_product(db: Session, product_id: int):
    return db.query(ProductModel).filter(ProductModel.product_id == product_id).first()

def get_product_by_code(db: Session, product_code: str):
    return db.query(ProductModel).filter(ProductModel.product_code == product_code).first()

def get_products(db: Session, skip: int = 0, limit: int = 100):
    return db.query(ProductModel).offset(skip).limit(limit).all()

def create_product(db: Session, product: ProductCreate):
    db_product = ProductModel(
        product_code=product.product_code,
        product_name=product.product_name,
        unit_of_measure=product.unit_of_measure
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product
</file>

<file path="backend/crud/crud_material.py">
from sqlalchemy.orm import Session
from backend.models.material import Material as MaterialModel
from backend.schemas.material import MaterialCreate

def get_material(db: Session, material_id: int):
    return db.query(MaterialModel).filter(MaterialModel.material_id == material_id).first()

def get_material_by_code(db: Session, material_code: str):
    return db.query(MaterialModel).filter(MaterialModel.material_code == material_code).first()

def get_materials(db: Session, skip: int = 0, limit: int = 100):
    return db.query(MaterialModel).offset(skip).limit(limit).all()

def create_material(db: Session, material: MaterialCreate):
    db_material = MaterialModel(
        material_code=material.material_code,
        material_name=material.material_name,
        unit_of_measure=material.unit_of_measure
    )
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material
</file>

<file path="backend/models/user.py">
from sqlalchemy import Column, Integer, String
from backend.database import Base # Assuming Base is defined in backend/database.py

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, index=True) # e.g., "admin", "planner", "viewer"
</file>

<file path="backend/models/product.py">
from sqlalchemy import Column, Integer, String
from backend.database import Base

class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String, unique=True, index=True)
    product_name = Column(String, index=True)
    unit_of_measure = Column(String)
</file>

<file path="backend/models/material.py">
from sqlalchemy import Column, Integer, String
from backend.database import Base

class Material(Base):
    __tablename__ = "materials"

    material_id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String, unique=True, index=True)
    material_name = Column(String, index=True)
    unit_of_measure = Column(String)
</file>

<file path="backend/database.py">
# This is a placeholder. You would typically set up your SQLAlchemy engine and session here.
# Example using SQLite:
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db" # Or your PostgreSQL/MySQL URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# You would also call Base.metadata.create_all(bind=engine) to create tables,
# likely in a separate script or during initial setup.
</file>

<file path="backend/core/security.py">
# Placeholder for password hashing utility
# In a real application, use a strong hashing library like passlib with bcrypt or Argon2
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
</file>

<file path="frontend/package.json">
{
  "name": "manufacturing-simulator-frontend",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.6.2",
    "vue": "^3.3.4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.2.3",
    "typescript": "^5.0.2",
    "vite": "^4.4.5",
    "vue-tsc": "^1.8.5"
  }
}
</file>

<file path="frontend/vite.config.ts">
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // Your backend API URL
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '/api')
      }
    }
  }
})
</file>

<file path="frontend/tsconfig.json">
{
  "compilerOptions": {
    "target": "ESNext",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "strict": true,
    "jsx": "preserve",
    "sourceMap": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "lib": ["ESNext", "DOM"],
    "types": ["vite/client"],
    "allowJs": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*.ts", "src/**/*.d.ts", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
</file>

<file path="frontend/index.html">
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Manufacturing Simulator</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
</file>

<file path="frontend/src/main.ts">
import { createApp } from 'vue'
import App from './App.vue'
import './styles/main.css'

createApp(App).mount('#app')
</file>

<file path="frontend/src/App.vue">
<template>
  <div>
    <h1>Manufacturing Management Simulator</h1>
    <UserList />
    <ProductList />
    <MaterialList />
  </div>
</template>

<script setup lang="ts">
import UserList from './components/UserList.vue';
import ProductList from './components/ProductList.vue';
import MaterialList from './components/MaterialList.vue';
</script>

<style scoped>
h1 {
  color: #333;
}
</style>
</file>

<file path="frontend/src/components/UserList.vue">
<template>
  <div>
    <h2>Users</h2>
    <ul>
      <li v-for="user in users" :key="user.user_id">
        {{ user.username }} ({{ user.email }} - {{ user.role }})
      </li>
    </ul>
    <p v-if="loading">Loading users...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchUsers } from '../services/userService';

interface User {
  user_id: number;
  username: string;
  email: string;
  role: string;
}

const users = ref<User[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    users.value = await fetchUsers();
  } catch (e: any) {
    error.value = `Failed to fetch users: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>
</file>

<file path="frontend/src/components/ProductList.vue">
<template>
  <div>
    <h2>Products</h2>
    <ul>
      <li v-for="product in products" :key="product.product_id">
        {{ product.product_name }} ({{ product.product_code }} - {{ product.unit_of_measure }})
      </li>
    </ul>
    <p v-if="loading">Loading products...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchProducts } from '../services/productService';

interface Product {
  product_id: number;
  product_code: string;
  product_name: string;
  unit_of_measure: string;
}

const products = ref<Product[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    products.value = await fetchProducts();
  } catch (e: any) {
    error.value = `Failed to fetch products: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>
</file>

<file path="frontend/src/components/MaterialList.vue">
<template>
  <div>
    <h2>Materials</h2>
    <ul>
      <li v-for="material in materials" :key="material.material_id">
        {{ material.material_name }} ({{ material.material_code }} - {{ material.unit_of_measure }})
      </li>
    </ul>
    <p v-if="loading">Loading materials...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchMaterials } from '../services/materialService';

interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  unit_of_measure: string;
}

const materials = ref<Material[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    materials.value = await fetchMaterials();
  } catch (e: any) {
    error.value = `Failed to fetch materials: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>
</file>

<file path="frontend/src/services/api.ts">
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1', // Matches the proxy in vite.config.ts
  headers: {
    'Content-Type': 'application/json',
  },
});

export default apiClient;
</file>

<file path="frontend/src/services/userService.ts">
import apiClient from './api';

interface User {
  user_id: number;
  username: string;
  email: string;
  role: string;
}

export const fetchUsers = async (): Promise<User[]> => {
  const response = await apiClient.get<User[]>('/users');
  return response.data;
};

// Add other user-related API calls here (e.g., createUser, getUserById)
</file>

<file path="frontend/src/services/productService.ts">
import apiClient from './api';

interface Product {
  product_id: number;
  product_code: string;
  product_name: string;
  unit_of_measure: string;
}

export const fetchProducts = async (): Promise<Product[]> => {
  const response = await apiClient.get<Product[]>('/products');
  return response.data;
};

// Add other product-related API calls here
</file>

<file path="frontend/src/services/materialService.ts">
import apiClient from './api';

interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  unit_of_measure: string;
}

export const fetchMaterials = async (): Promise<Material[]> => {
  const response = await apiClient.get<Material[]>('/materials');
  return response.data;
};

// Add other material-related API calls here
</file>

<file path="frontend/src/styles/main.css">
/* Global styles for the application */
body {
  font-family: 'Arial', sans-serif;
  margin: 20px;
  background-color: #f4f7f6;
  color: #333;
}

h1, h2 {
  color: #2c3e50;
}

ul {
  list-style: none;
  padding: 0;
}

li {
  background-color: #ffffff;
  margin-bottom: 8px;
  padding: 10px;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
</style>
</file>

<file path=".env">
# Backend Configuration
SECRET_KEY=a_very_secret_key_for_development_only
DATABASE_URL=sqlite:///./sql_app.db # Example for SQLite

# Frontend Configuration (if needed, though Vite handles most via vite.config.ts)
# VITE_API_BASE_URL=http://localhost:8000/api/v1
</file>