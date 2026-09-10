"""나레이션 JSON → 슬라이드별 wav + 문장 타임코드(자막용).

사용: python make_tts2.py <narration.json> <out_dir> [--voice sunhi] [--rate +6%] [--gap 0.35]

- 문장 단위로 TTS 를 만들고, 앞뒤 무음을 잘라낸 뒤 문장 사이에 일정한 호흡(gap)을 넣어 잇는다.
  → 문장 간 리듬이 일정해지고, 자막 타임코드가 오디오 길이에서 바로 나온다.
- 발음용 대본은 make_tts.to_speak() 규칙(영문 글자별 읽기, LAXS=랙스)을 그대로 쓴다.
- 출력: {id}.wav (48k/stereo/16bit), {id}.cues.json [{text, speak, start, end}]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import wave

import edge_tts
import imageio_ffmpeg
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_tts import VOICES, to_speak  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


async def synth(text: str, voice: str, out: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def mp3_to_pcm(mp3: str) -> np.ndarray:
    r = subprocess.run(
        [FFMPEG, "-loglevel", "error", "-i", mp3, "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(r.stdout, dtype="<i2").reshape(-1, 2).astype(np.float32) / 32768.0


def trim(pcm: np.ndarray, thresh: float = 0.004, keep: float = 0.06) -> np.ndarray:
    """앞뒤 무음을 잘라내되 keep 초는 남긴다(숨 붙는 소리 보호)."""
    mag = np.abs(pcm).max(axis=1)
    idx = np.where(mag > thresh)[0]
    if len(idx) == 0:
        return pcm
    k = int(keep * SR)
    a, b = max(0, idx[0] - k), min(len(pcm), idx[-1] + k)
    return pcm[a:b]


def write_wav(path: str, pcm: np.ndarray) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())


def main(argv: list[str]) -> None:
    spec, out_dir = argv[0], argv[1]
    voice = VOICES.get(argv[argv.index("--voice") + 1], argv[argv.index("--voice") + 1]) if "--voice" in argv else VOICES["sunhi"]
    rate = argv[argv.index("--rate") + 1] if "--rate" in argv else "+6%"
    gap = float(argv[argv.index("--gap") + 1]) if "--gap" in argv else 0.35

    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_sentences")
    os.makedirs(tmp, exist_ok=True)
    items = json.load(open(spec, encoding="utf-8"))

    for it in items:
        sents = split_sentences(it["text"])
        speaks = split_sentences(it.get("speak") or to_speak(it["text"]))
        if len(sents) != len(speaks):
            raise SystemExit(f"{it['id']}: 표시 문장 {len(sents)}개 ≠ 발음 문장 {len(speaks)}개")
        pcm_parts, cues, cursor = [], [], 0.0
        silence = np.zeros((int(gap * SR), 2), dtype=np.float32)
        for i, (s, sp) in enumerate(zip(sents, speaks)):
            mp3 = os.path.join(tmp, f"{it['id']}_{i:02d}.mp3")
            asyncio.run(synth(sp, voice, mp3, rate))
            pcm = trim(mp3_to_pcm(mp3))
            dur = len(pcm) / SR
            cues.append({"text": s, "speak": sp, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
            pcm_parts.append(pcm)
            cursor += dur
            if i < len(sents) - 1:
                pcm_parts.append(silence)
                cursor += gap
        write_wav(os.path.join(out_dir, it["id"] + ".wav"), np.concatenate(pcm_parts))
        json.dump(cues, open(os.path.join(out_dir, it["id"] + ".cues.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        left = [w for c in cues for w in re.findall(r"[A-Za-z]{2,}", c["speak"])]
        print(f"{it['id']:16s} {len(sents)}문장 {cursor:5.1f}s  미치환:{left or '-'}", flush=True)
    print(f"voice={voice} rate={rate} gap={gap}s → {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
