# -*- coding: utf-8 -*-
"""배포 관리(control plane) 패키지 — **업무 제품과 섞지 않는다.**

[구현 인계서 §2-12] 관리툴 코드는 `ops_control/` · `ops_console/` · `deploy/agent/` 에
둔다. 업무 `App.tsx` 나 `core/db` 에 섞지 않는다 — 섞이는 순간 업무 DB 이관 일정이
관리 UI 일정에 묶이고, 업무 인증 경계가 관리 권한 경계와 한 덩어리가 된다.

⚠️ 그래서 이 패키지는 **제품 기동 경로에서 import 되지 않는다.** 산출물 허용목록에도
  들어 있지 않다(`scripts/release_artifact.py`) — 관리 평면은 따로 배포된다.
"""
