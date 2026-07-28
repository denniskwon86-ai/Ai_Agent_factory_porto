# LS MnM 온산공장 실제급 제조 합성 데이터 생성 명세서 (Data Generation Spec)

> **상태**: To-Be 시드 데이터 명세서  
> **생성 목적**: 문서 데이터(M1~M4) 내 도메인 물리/화학/재무 파라미터를 결합하여 실제 제조 기업(LS MnM)과 동일한 수준의 정밀 시드 데이터 생성  
> **관련 문서**: `design_enterprise_context_master.md`, `battery_material_m1.json`, `copper_smelting_m2.json`, `global_standard_m3.json`, `digital_twin_simulation_m4.json`

---

## 1. 엔터프라이즈 컨텍스트 계층 (Enterprise Context Nodes)

`design_enterprise_context_master.md` 규격에 따라 LS 그룹 및 LS MnM의 실제 조직 계층 노드와 엣지를 모델링합니다.

```text
tenant-ls-group-001 (LS 그룹 테넌트)
└─ node-ls-group (지주사: LS 그룹)
   └─ node-ls-mnm (법인: LS MnM, 업종: 동제련 및 이차전지 소재)
      ├─ node-ls-mnm-shared (전사 공통 지원: 재무/회계/IT)
      ├─ node-ls-mnm-smelting-bu (사업부: 동제련 사업부)
      │  └─ node-ls-mnm-onsan-plant1 (사업장: 온산 제1공장 — 동제련/전해)
      │     ├─ line-flash-smelting (자용로 공정)
      │     ├─ line-converter (전로 공정)
      │     └─ line-electro-refining (전해 정제 공정)
      └─ node-ls-mnm-battery-bu (사업부: 배터리 소재 사업부)
         └─ node-ls-mnm-onsan-plant2 (사업장: 온산 제2공장 — 황산니켈/수산화리튬)
            ├─ line-leaching-dissolution (침출/침전 공정)
            ├─ line-solvent-extraction (용매 추출 SX 공정)
            └─ line-crystallization (결정화/원심분리 공정)
```

---

## 2. 품목 마스터 & BOM 수율 체계 (Material & Yield Analytics)

### 2.1 동제련 사업부 (온산 제1공장)
* **원자재**: 동정광(`RM-CuCON-001`, 30% Cu, LME 연동가 $9,500/Ton 기준 60일 리드타임)
* **공정 중간재**: 동매트(`WIP-MATTE-001`, 60% Cu) → 아노드동(`WIP-ANODE-001`, 99% Cu)
* **완제품 & 부산물**:
  * 전기동(`FG-CATHODE-001`, 99.99% Cu, 수율 **98.0%**)
  * 부산물: 황산(`BP-H2SO4-001`, $120/Ton, 정광 1톤당 0.88톤 산출), 금괴(`BP-GOLD-001`, LBMA 시세 $2,350/oz)

### 2.2 배터리 소재 사업부 (온산 제2공장)
* **원자재**: MHP(`RM-MHP-001`, $15,000/Ton, 리드타임 45일), 황산 98%(`RM-H2SO4-001`, $150/Liter)
* **공정 중간재**: 조황산니켈 용액(`WIP-NiSO4-001`)
* **완제품**:
  * 고순도 황산니켈 결정(`FG-NiSO4-001`, $22,000/Ton, 기준 수율 **94.0%**, 스크랩 회수율 **5.0%**)
  * 배터리급 수산화리튬(`FG-LiOH-001`, $45,000/Ton)

---

## 3. 설비 신뢰성 & 디지털 트윈 시뮬레이션 (Equipment & Telemetry)

### 3.1 설비 신뢰성 마모 및 수리 확률분포 (Weibull & Exponential)
* **자용로 (EQ-FLASH-01)**: 용량 150 Ton/hr, 목표 OEE 92%, MTBF(Weibull k=2.5, λ=1440시간), MTTR(Exponential λ=0.2, 평균 5시간).
* **침출 용해조 (EQ-DIS-01)**: 용량 5 Ton/hr, 목표 OEE 85%, MTBF 720시간, MTTR 8시간.
* **용매 추출기 (EQ-SX-01)**: 용량 4.5 Ton/hr, 목표 OEE 90%, MTBF 1440시간, MTTR 12시간.

### 3.2 1Hz 센서 스트림 데이터 합성 (Telemetry Stream)
* **온도 센서 (`Sensor_Temperature`)**: 850°C ~ 1,250°C (Normal dist μ=1150, σ=15)
* **모터 진동 센서 (`Sensor_Vibration`)**: ISO 22400 기준 Normal(2.1 mm/s), Warning(4.5 mm/s), Critical Shutdown(7.1 mm/s)
* **AGV 위치 & 물류 물리학**: 3D 가상 노드 좌표(Node_A_Flash_Furnace → Node_B_Refinery_Cell, 거리 150m, AGV 속도 2.0 m/s)

---

## 4. 품질 통계 (SPC) & SIOP 손익 모델

### 4.1 ICP-OES/MS 불순물 품질 분석 (Gaussian & Cpk)
* **황산니켈 코발트(Co) 불순물**: 한계치 10.0 PPM, Gaussian(μ=5.0, σ=2.0), 목표 Cpk = **1.33**
* **전기동 납(Pb) 불순물**: 한계치 5.0 PPM, Gaussian(μ=1.5, σ=0.8), 목표 Cpk = **1.67**

### 4.2 SIOP 경영 및 손익 원장 (P&L Simulation)
* **시세 변수**: LME 니켈 $16,500/Ton, LME 동 $9,500/Ton, 환율 1,350 KRW/USD
* **제조 경비**: 노무비 $35~40/hr, 전력비 $0.12/kWh, 재고 보유 비용률 연 15%
* **SLA 제재**: 납기 지연 일단가 2% 감가, 품질 클레임 패널티 3.0배 적용.
