"""나레이션 JSON → 슬라이드별 mp3 (Microsoft Edge Neural TTS, edge-tts).

사용:
  python make_tts.py <narration.json> <out_dir> [--voice ko-KR-SunHiNeural] [--rate +0%]
  python make_tts.py --compare "문장" <out_dir>      # 세 음성 비교 샘플

- 표시용 대본(text)은 그대로 두고, 발음용 대본(speak)을 만들어 TTS 에 넣는다.
- 영문 약어는 글자별 한글 음절로 읽는다(AX → 에이엑스). 브랜드명 LAXS 는 문서 정의대로 「랙스」.
- 항목에 "speak" 가 있으면 자동 치환 대신 그 값을 쓴다.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import edge_tts

VOICES = {
    "sunhi": "ko-KR-SunHiNeural",       # 여성
    "injoon": "ko-KR-InJoonNeural",     # 남성
    "hyunsu": "ko-KR-HyunsuMultilingualNeural",  # 남성·다국어
}

# 문서가 발음을 정의한 고유명·관례 표기 — 일반 규칙보다 먼저 적용한다(긴 것 우선).
LEXICON = [
    ("LAXS-M", "랙스 엠"),
    ("LAXS", "랙스"),
    ("LS MnM", "엘에스 엠엔엠"),
    ("MnM", "엠엔엠"),
    ("DEMO", "데모"),
]

LETTER = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def to_speak(text: str) -> str:
    s = text
    for src, dst in LEXICON:
        s = s.replace(src, dst)
    # 남은 대문자 약어(1~6자)는 글자별 독립 음절로 읽는다. 'AX' → '에이엑스', 'ERP' → '이알피'
    # \b 는 한글도 단어 문자로 보므로 'AX를'·'LPL과' 가 걸리지 않는다 — 영문자 경계로만 자른다.
    s = re.sub(r"(?<![A-Za-z])([A-Z]{1,6})(?![A-Za-z])", lambda m: "".join(LETTER[c] for c in m.group(1)), s)
    # 슬래시 표기(PI/IT)는 쉼표 호흡으로
    s = s.replace("/", ", ")
    return s


async def synth(text: str, voice: str, out: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--compare":
        sentence, out_dir = argv[1], argv[2]
        os.makedirs(out_dir, exist_ok=True)
        speak = to_speak(sentence)
        print("speak:", speak)
        for key, v in VOICES.items():
            out = os.path.join(out_dir, f"compare_{key}.mp3")
            asyncio.run(synth(speak, v, out, "+0%"))
            print(out)
        return

    spec, out_dir = argv[0], argv[1]
    voice = VOICES["sunhi"]
    rate = "+0%"
    if "--voice" in argv:
        voice = argv[argv.index("--voice") + 1]
        voice = VOICES.get(voice, voice)
    if "--rate" in argv:
        rate = argv[argv.index("--rate") + 1]

    os.makedirs(out_dir, exist_ok=True)
    items = json.load(open(spec, encoding="utf-8"))
    log = []
    for it in items:
        speak = it.get("speak") or to_speak(it["text"])
        out = os.path.join(out_dir, it["id"] + ".mp3")
        asyncio.run(synth(speak, voice, out, rate))
        log.append({"id": it["id"], "speak": speak})
        print(f"{it['id']:16s} {len(speak):4d}자  {speak[:48]}…", flush=True)
    json.dump(log, open(os.path.join(out_dir, "_speak_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"voice={voice} rate={rate} → {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
