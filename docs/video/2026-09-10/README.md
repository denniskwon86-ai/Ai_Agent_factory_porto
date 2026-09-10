# LAXS-M 소개 영상 제작 패키지

작성: Codex · 2026-09-10 · 상태: 내부 검토용 콘셉트 샘플

- `LAXS-M_20s_sample.mp4`: 한국어 내레이션·자막·배경음이 포함된 20초 영상
- `VIDEO_STRATEGY.md`: 문서 분석, 메시지, 90초 본편 기획, 20초 스토리보드
- `storyboard.jpg`: 주요 장면을 한눈에 보는 검토 이미지
- `captions.srt`: 별도 자막 파일
- `render_video.py`, `make_voice.ps1`: 수정·재제작용 원본
- `verification.json`: 길이·프레임·오디오 및 파일 검증 결과

샘플은 제품의 지향 구조를 설명하는 모션그래픽입니다. 실제 제품 조작 녹화나 실데이터 성과 증명이 아닙니다. 제품 코드·DB·공식 문서는 수정하지 않았으며, 제품 구현 관문을 추가 통과한 작업도 아닙니다.


## 재제작

Windows에서 Python 3, Pillow, NumPy, imageio-ffmpeg와 한국어 Microsoft Heami Desktop 음성을 사용한다. `render_video.py`의 `STARTS`, `CAPTIONS`, `scene()`에서 시간·문구·그림을 수정한다. 음성 문구는 `make_voice.ps1`과 자막을 함께 수정한다.

프로젝트 루트에서 실행:

```powershell
python -m pip install --target tmp/laxs-video-deps imageio-ffmpeg
& docs/video/2026-09-10/make_voice.ps1
python docs/video/2026-09-10/render_video.py
```

현재 세션에서는 Codex 번들 Python의 Pillow·NumPy를 재사용했다. 일반 Python에서는 `pip install pillow numpy`가 추가로 필요할 수 있다. 음성과 직접 합성한 배경음의 WAV 원본은 `audio/`에 남겼다. 공식 로고는 기존 `docs/official/assets/brand-v0.3/`에서 읽는다.
