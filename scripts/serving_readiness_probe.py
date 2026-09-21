# -*- coding: utf-8 -*-
"""[P2 · DEP-06] **서빙 준비도 탐침** — 노드 «위에서» 돌린다.

승격 자동화는 이 명령의 **종료 코드**로 판단한다.

    0  READY     이 노드에 트래픽을 넘겨도 된다
    1  FAIL      확인된 실패 — 승격 금지
    2  UNKNOWN   모른다 — **승격 금지**(초록이 아니다)

★ 셋을 «다른 코드» 로 낸다. `0 / 1` 둘로 접으면 「모른다」가 「실패」에 섞여 원인을
  못 찾거나, 더 나쁘게는 성공 쪽으로 접힌다.

## 왜 HTTP 가 아니라 명령인가

준비도는 LB·배포 자동화가 읽는 값이라 **인증을 걸면 못 쓰고, 안 걸면 내부가 샌다.**
그 경계를 내가 임의로 정하지 않는다. 노드 위에서 도는 명령은 그 문제를 만들지 않고도
같은 판정을 준다. HTTP 노출(어느 포트·어떤 인증)은 **승인 경계 결정**으로 남긴다.

## 이 명령이 하지 않는 것

외부 호출 0 · LLM 0 · DDL 0 · seed 0 · 쓰기 0. 없는 DB 파일을 **만들지 않는다**.
경로·SQL·접속 정보를 출력하지 않는다(사유는 닫힌 코드 목록).

사용:
    python scripts/serving_readiness_probe.py \
        --shared-dir /srv/afs/library --role api --started api
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import serving_readiness as sr  # noqa: E402

#: 배포자가 심는 값. **없으면 UNKNOWN 이다** — 「아마 맞겠지」로 승격하지 않는다.
ENV_DIGEST = "AFS_ARTIFACT_DIGEST"
ENV_CONFIG = "AFS_CONFIG_FINGERPRINT"

EXIT = {sr.READY: 0, sr.FAIL: 1, sr.UNKNOWN: 2}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서빙 준비도 탐침 (읽기 전용)")
    ap.add_argument("--settings", default="", help="설치 설정 경로 (기본: data/instance.json)")
    ap.add_argument("--shared-dir", action="append", default=[],
                    help="공유여야 하는 디렉터리 (여러 번)")
    ap.add_argument("--role", action="append", default=[],
                    help="이 노드가 맡기로 한 역할 (여러 번)")
    ap.add_argument("--started", action="append", default=[],
                    help="실제로 떠 있다고 «관측된» 역할 (여러 번)")
    ap.add_argument("--expect-digest", default="", help="요구되는 artifact digest")
    ap.add_argument("--expect-config", default="", help="요구되는 설정 지문")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings_path = args.settings or os.path.join(root, "data", "instance.json")

    report = sr.collect(
        settings_path=settings_path,
        shared_dirs=args.shared_dir,
        declared_roles=args.role,
        started_roles=args.started,
        running_digest=os.environ.get(ENV_DIGEST, ""),
        running_config=os.environ.get(ENV_CONFIG, ""),
        expected_digest=args.expect_digest,
        expected_config=args.expect_config,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    #: ⚠️ 모르는 판정값이 오면 **성공으로 접지 않는다.**
    return EXIT.get(report.verdict, 2)


if __name__ == "__main__":
    raise SystemExit(main())
