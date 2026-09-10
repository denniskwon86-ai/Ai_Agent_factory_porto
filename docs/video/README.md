# LAXS-M 소개 영상

최신 본편은 **B 여성 성우 톤을 적용한 2분 38초 영상**입니다. 현업이 SW·에이전트·업무별 시뮬레이터를 직접 만들고 운영해 데이터를 축적하며, 이를 전사 판단으로 연결하는 흐름을 실제 제품 시연과 함께 설명합니다.

- [최신 본편 MP4](2026-09-11-final-film/LAXS-M_mainfilm_B_female.mp4)
- [전체 내레이션 MP3](2026-09-11-final-film/LAXS-M_B_narration.mp3)
- [최종 대본](2026-09-11-final-film/FINAL_SCRIPT.md)
- [제작 기록·검증 결과·장면 구성](2026-09-11-final-film/README.md)
- [기획 및 제품 문서 분석](2026-09-10/VIDEO_STRATEGY.md)
- [여성 음성 비교 샘플](2026-09-11-voice-audition/README.md)

## 버전 기록

| 폴더 | 내용 |
|---|---|
| 2026-09-10 | 최초 20초 샘플과 기획안 |
| 2026-09-10-mainfilm | 최초 실제 시연 본편과 시뮬레이션 시연 |
| 2026-09-10-creator-film | SW·에이전트·시뮬레이터 제작 기능을 보강한 무음 검토본 |
| 2026-09-11-voice-audition | 여성 아나운서·성우 톤 비교 |
| 2026-09-11-final-film | 선택한 B 목소리를 적용한 최신 본편 |

이전 버전의 승인 대기 표기는 해당 제작 시점의 기록입니다. 이후 사용자의 명시적 동의로 합성한 최종 결과와 실제 시연 범위는 최신 제작 기록을 따릅니다. 엔딩은 음성 서비스의 일일 한도로 이미 생성된 B 음성의 핵심 소개 문장을 재사용했습니다.

## 보관 및 재편집

최종 매체, 실제 녹화 원본, 최종 음성 WAV, 대본·메타데이터, 편집 스크립트를 보관합니다. 장면별 렌더링 캐시, 화면 탐색 기록, 중복 녹화, 로컬 서버 PID 등은 Git에서 제외하며 로컬 파일은 유지합니다. 원본 녹화는 시연 환경과 합성 데이터에 기반한 제작 당시 화면입니다.

편집 스크립트는 Windows의 맑은 고딕을 사용합니다. Python 환경에 Pillow, NumPy, imageio-ffmpeg, edge-tts가 필요하며, 음성 재합성에는 google-genai와 python-dotenv가 추가로 필요합니다. 최종 음성은 이미 보관되어 있어 로컬 렌더링에 외부 음성 호출은 필요하지 않습니다.

```powershell
python docs/video/2026-09-11-final-film/render_final.py --check-sources
python docs/video/2026-09-11-final-film/render_final.py --resume
```

사용자가 요청한 소개 자료 제작·보관 작업이며, 제품 기능의 G0~G9 구현 관문이 새로 통과했다는 의미는 아닙니다.
