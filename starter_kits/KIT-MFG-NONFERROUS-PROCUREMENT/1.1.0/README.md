# KIT-MFG-NONFERROUS-PROCUREMENT 1.1.0

- 회사: AFS 데모소재그룹(명시적 가상기업)
- 데이터: SYNTHETIC
- 프로필: Quick 6개월, Full 36개월
- 데이터셋: 35개
- 주의: 실제 경영 의사결정과 예측 정확도 증명에 사용할 수 없습니다.

1. 데이터 생성: `venv\Scripts\python.exe scripts\generate_sample_company_starter_kit.py`
2. 데이터 검증: `venv\Scripts\python.exe scripts\validate_sample_company_starter_kit.py`
3. Excel 생성: `venv\Scripts\python.exe scripts\generate_sample_company_excel_templates.py`
4. Excel 재계산: `powershell -ExecutionPolicy Bypass -File scripts\recalculate_sample_company_excel_templates.ps1`
5. Excel 검증: `venv\Scripts\python.exe scripts\validate_sample_company_excel_templates.py`
