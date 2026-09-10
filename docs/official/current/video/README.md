# LAXS-M 설명 영상

공식 문서(`docs/official/current/pdf/` 최신 판본)를 소스로 만드는 나레이션 영상의 **정본**은 이 폴더의 기획서와 대본이다. 영상 파일(mp4)은 크기 때문에 git 에 넣지 않고 아래 명령으로 다시 만든다.

| 파일 | 역할 |
|---|---|
| `LAXS-M_AX_PLATFORM_INTRO_VIDEO_PLAN.md` | 기획서 — 목적·소스 문서·구성·나레이션 원칙·화면·BGM·남은 결정·변경 이력 |
| `laxs-m-ax-platform-intro.narration.json` | 대본 — 슬라이드 순서, 소스 PDF·페이지, 표시용 문장. 발음용 문장은 도구가 규칙으로 만든다 |
| `../../../../scripts/video/` | 제작 도구 — `make_tts2.py`(문장별 음성·자막 타임코드), `make_bgm.py`(합성 BGM), `build_video2.py`(렌더·합성) |

## 재현

```text
.venv\Scripts\python.exe -m pip install -r scripts\video\requirements.txt
.venv\Scripts\python.exe scripts\video\make_tts2.py docs\official\current\video\laxs-m-ax-platform-intro.narration.json output\video\main\audio --voice sunhi --rate +6% --gap 0.35
.venv\Scripts\python.exe scripts\video\build_video2.py docs\official\current\video\laxs-m-ax-platform-intro.narration.json output\video\main\LAXS-M_AX_Platform_Intro.mp4 --work-dir output\video\main --bgm auto
```

- 결과: `output/video/main/LAXS-M_AX_Platform_Intro.mp4` (1920×1080, 약 4분 18초). `output/` 은 git 추적 제외다.
- 소스 PDF 가 개정되면 대본의 `pdf`·`page` 만 맞추고 두 명령을 다시 실행한다.
- ffmpeg 는 `imageio-ffmpeg` 가 번들로 제공한다. 한글 폰트는 Windows 의 Noto Sans KR 또는 맑은 고딕을 쓴다.

## 주의

- 음성은 **Microsoft Edge Neural(`edge-tts`)** — 온라인 방식이라 대본 문장이 Microsoft 음성 서비스로 전송된다. 대본에는 대외 배포 문서 수준의 문장만 쓴다.
- 영문 약어는 도구가 글자별 한글 음절로 바꿔 읽는다(`AX → 에이엑스`). 브랜드명 `LAXS` 만 문서 정의대로 「랙스」. 규칙은 `scripts/video/make_tts.py` 의 `LEXICON`·`to_speak()`.
- BGM 은 로컬에서 합성한 앰비언트 패드라 라이선스 표기 의무가 없다. 상용·CC 음원으로 바꾸면 `--bgm <파일>` 로 교체하고 음원 라이선스의 크레딧 규정을 따른다.
- 시뮬레이션 화면의 수치는 합성 데모 데이터이며 나레이션에서도 그렇게 말한다. 실제 경영 수치로 오해될 문장을 넣지 않는다.
