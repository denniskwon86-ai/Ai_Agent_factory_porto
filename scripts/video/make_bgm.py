"""라이선스 걱정 없는 배경음 — 로컬에서 합성한 앰비언트 패드.

사용: python make_bgm.py <초> <out.wav>
- 48 kHz 스테레오 16-bit. 코드 진행(Cmaj7 → Am7 → Fmaj7 → Gadd9) 8초씩 순환.
- 사인파 기반 패드 + 옥타브 위 벨 톤 아르페지오. 좌우 미세 디튠으로 폭을 준다.
- 배경용이므로 대비를 낮게(부드러운 어택·느린 호흡). 믹스 단계에서 -16 dB 안팎으로 깐다.
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 48000
CHORDS = [  # Hz (3옥타브 근방)
    [130.81, 164.81, 196.00, 246.94],  # Cmaj7
    [110.00, 130.81, 164.81, 196.00],  # Am7
    [87.31, 110.00, 130.81, 164.81],   # Fmaj7
    [98.00, 123.47, 146.83, 220.00],   # Gadd9
]
CHORD_SEC = 8.0
XFADE_SEC = 1.2


def pad_tone(freq: float, n: int, detune: float) -> np.ndarray:
    t = np.arange(n) / SR
    f = freq * (1 + detune)
    return (np.sin(2 * np.pi * f * t)
            + 0.30 * np.sin(2 * np.pi * 2 * f * t)
            + 0.10 * np.sin(2 * np.pi * 3 * f * t))


def bell(freq: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    env = np.exp(-t * 1.8)
    return (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 2.01 * freq * t)) * env


def main(duration: float, out: str) -> None:
    n_total = int(duration * SR) + SR * 2
    L = np.zeros(n_total)
    R = np.zeros(n_total)
    seg = int(CHORD_SEC * SR)
    xf = int(XFADE_SEC * SR)

    # 패드: 코드마다 겹쳐 페이드하며 순환
    pos, k = 0, 0
    while pos < n_total:
        chord = CHORDS[k % len(CHORDS)]
        n = min(seg + xf, n_total - pos)
        env = np.ones(n)
        env[:xf] = np.linspace(0, 1, xf)[: min(xf, n)]
        tail = min(xf, n)
        env[-tail:] *= np.linspace(1, 0, tail)
        for f in chord:
            L[pos:pos + n] += pad_tone(f, n, -0.0012) * env
            R[pos:pos + n] += pad_tone(f, n, +0.0012) * env
        # 저역 루트(옥타브 아래) — 바닥을 받쳐 준다
        L[pos:pos + n] += 0.6 * np.sin(2 * np.pi * (chord[0] / 2) * np.arange(n) / SR) * env
        R[pos:pos + n] += 0.6 * np.sin(2 * np.pi * (chord[0] / 2) * np.arange(n) / SR) * env
        pos += seg
        k += 1

    # 느린 호흡(0.08 Hz) — 정적인 패드에 미세한 움직임
    t_all = np.arange(n_total) / SR
    breath = 0.85 + 0.15 * np.sin(2 * np.pi * 0.08 * t_all)
    L *= breath
    R *= breath

    # 벨 아르페지오: 2초마다 현재 코드의 음 하나를 두 옥타브 위에서
    rng = np.random.default_rng(7)
    step = int(2.0 * SR)
    bell_len = int(3.5 * SR)
    for i, pos in enumerate(range(int(1.0 * SR), n_total - bell_len, step)):
        chord = CHORDS[(pos // seg) % len(CHORDS)]
        f = chord[rng.integers(0, len(chord))] * 4
        b = bell(f, bell_len) * 0.22
        pan = 0.35 + 0.3 * rng.random()          # 좌우로 흩어 놓는다
        L[pos:pos + bell_len] += b * (1 - pan)
        R[pos:pos + bell_len] += b * pan

    # 전체 페이드 인/아웃, 정규화
    fi, fo = int(2.5 * SR), int(4.0 * SR)
    L[:fi] *= np.linspace(0, 1, fi); R[:fi] *= np.linspace(0, 1, fi)
    L[-fo:] *= np.linspace(1, 0, fo); R[-fo:] *= np.linspace(1, 0, fo)
    peak = max(np.abs(L).max(), np.abs(R).max())
    L, R = L / peak * 0.9, R / peak * 0.9

    data = np.stack([L, R], axis=1)[: int(duration * SR)]
    pcm = (data * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"BGM {duration:.1f}s → {out}")


if __name__ == "__main__":
    main(float(sys.argv[1]), sys.argv[2])
