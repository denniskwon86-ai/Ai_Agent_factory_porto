import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tmp/laxs-video-deps'))
import imageio_ffmpeg

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
items = json.loads((OUT / 'auditions.json').read_text(encoding='utf-8'))
for item in items:
    target = OUT / (item['id'] + '.mp3')
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(OUT / item['file']), '-af',
                    'loudnorm=I=-16:TP=-1.5:LRA=7', '-ar', '48000',
                    '-c:a', 'libmp3lame', '-b:a', '192k', str(target)], check=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error',
                    '-i', str(target), '-f', 'null', '-'], check=True)
    item['preview_file'] = target.name
    item['decode_check'] = 'passed'
(OUT / 'verification.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')

timeline = json.loads((ROOT / 'docs/video/2026-09-10-creator-film/picture_timeline.json').read_text(encoding='utf-8'))
approval = ['# 본편 전체 내레이션 — Google Gemini 전송 검토본', '',
            '상태: 사용자 승인 대기. 이 파일의 제품 내레이션은 아직 새 음성 서비스로 전송하지 않았습니다.', '',
            '목적: 여성 아나운서 또는 성우 톤으로 본편 전체 음성을 통일하고, 실제 기능 시연 영상에 맞춰 재편집합니다.', '',
            '수신 서비스: Google Gemini API의 음성 생성 모델 `gemini-3.1-flash-tts-preview`.', '',
            '전송 예정 내용: 아래 12개 내레이션 문장과 여성 목소리·속도·억양·쉼을 지정하는 연출 지시문. 프로젝트 문서, 소스 코드, 녹화 화면, 로그인 정보는 전송 대상에 포함하지 않습니다.', '',
            '기본 연출안: 성인 여성의 부드러운 중음역, 자연스러운 표준 한국어, 차분한 기업 소개 내레이션. 문장마다 의미에 맞게 쉬고, 과장된 광고 억양이나 기계적인 등속 낭독을 피합니다. 실제 사람이 녹음한 음성이 아닌 AI 생성 음성입니다.', '',
            '기존 Microsoft Edge 전송 요청과는 다른 서비스이므로, 기존 요청에 대한 승인으로 간주하지 않습니다.', '']
for i, scene in enumerate(timeline['scenes'], 1):
    approval.extend([f"## {i:02d}. {scene['title']}", '', scene['text'], ''])
(OUT / 'FULL_NARRATION_APPROVAL.md').write_text('\n'.join(approval), encoding='utf-8')
(OUT / 'README.md').write_text('''# 여성 내레이션 비교 샘플

- A_announcer.mp3: 또렷하고 차분한 아나운서 톤을 지시한 샘플. Kore, 12.60초.
- B_warm_narrator.mp3: 따뜻하고 부드러운 성우 톤을 지시한 샘플. Sulafat, 13.68초.
- 두 파일은 Google Gemini로 생성한 AI 음성입니다. 실제 성우 녹음은 아닙니다.
- 같은 일반 문장을 사용했습니다. 회사명과 비공개 제품 설명은 포함하지 않았습니다.
- 음량은 -16 LUFS 목표, 피크 -1.5 dBTP 목표로 정규화했습니다. MP3 전체 디코딩 검사를 통과했습니다.
- 자연스러움과 선호도는 사용자가 직접 들어 보고 판단할 수 있도록 원본 WAV와 재생용 MP3를 함께 보관합니다.

샘플 문장:
> 더 나은 변화는, 현장에서 시작됩니다. 오늘의 작은 경험이 쌓여, 내일의 선택을 바꿉니다. 이제, 다음 가능성을 만나보세요.

본편은 SW 생성기, 현업 에이전트 제작, 업무 영역별 시뮬레이터 생성·운영과 데이터 축적을 포함하는 약 152초 영상 구성에 맞춥니다. 현재 본편의 새 음성 합성은 승인 대기 상태입니다. 전송할 전체 내레이션은 FULL_NARRATION_APPROVAL.md에서 검토할 수 있습니다.

음성 연출 기능 공식 문서: https://ai.google.dev/gemini-api/docs/speech-generation
''', encoding='utf-8')
print('Two MP3 previews decoded successfully; full narration approval document prepared.')
