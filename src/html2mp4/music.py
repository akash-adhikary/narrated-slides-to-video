"""Generate royalty-free background music beds with plain DSP synthesis (no AI).

Each bed is a seamless loop (chords Am7 - Fmaj7 - Cadd9 - G at 80 BPM) designed to sit
quietly under narration. Beds are 48 kHz / 24-bit stereo FLAC, generated once and cached.

usage: html2mp4-music [OUT_DIR]       # writes every style (default: current directory)
"""
import pathlib, sys
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
BPM = 80
BEAT = 60 / BPM
CHORD = 8 * BEAT                       # two bars per chord = 6 s
PROG = [                               # (bass note, voicing) in MIDI
    (45, [57, 60, 64, 67]),            # Am7
    (41, [53, 57, 60, 64]),            # Fmaj7
    (48, [55, 60, 62, 64]),            # Cadd9
    (43, [55, 59, 62, 67]),            # G
]
CYCLES = 2
LOOP = len(PROG) * CHORD * CYCLES      # 48 s loop
TAIL = 5.0
STYLES = ("gentle-pulse", "calm-pad", "warm-keys")
rng = np.random.default_rng(7)


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
def t_axis(dur): return np.arange(int(dur * SR)) / SR
def lowpass(x, fc, order=2): return sosfilt(butter(order, fc, fs=SR, output="sos"), x, axis=-1)


def add(buf, start, sig):
    i = int(start * SR); buf[:, i:i + sig.shape[-1]] += sig[:, : buf.shape[1] - i]


def pan(sig, p):                       # p in [-1, 1], constant power
    a = (p + 1) * np.pi / 4
    return np.stack([sig * np.cos(a), sig * np.sin(a)])


def ar_env(t, attack, hold, release):
    e = np.clip(t / attack, 0, 1)
    rel = np.clip(1 - (t - attack - hold) / release, 0, 1)
    return (e * np.where(t > attack + hold, rel, 1)) ** 2


def pad_note(m, dur, cutoff):
    """Detuned band-limited saws, separate for L/R for width."""
    f, t = hz(m), t_axis(dur)
    out = []
    for detunes in ((-7, 0, 5), (-5, 0, 7)):
        s = np.zeros_like(t)
        for c in detunes:
            fd = f * 2 ** (c / 1200)
            for n in range(1, int(min(cutoff * 1.6, 6000) / fd) + 1):
                s += np.sin(2 * np.pi * fd * n * t + rng.uniform(0, 2 * np.pi)) / n
        out.append(s)
    return lowpass(np.array(out) / 6, cutoff)


def pluck(m, dur=0.9, decay=0.28):
    f, t = hz(m), t_axis(dur)
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    return lowpass(s * np.exp(-t / decay) * (1 - np.exp(-t / 0.004)), 3200)


def epiano(m, dur=3.0):
    """Two-operator FM electric piano."""
    f, t = hz(m), t_axis(dur)
    idx = 1.6 * np.exp(-t / 0.35)
    s = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    s += 0.05 * np.sin(2 * np.pi * f * 14 * t) * np.exp(-t / 0.03)        # tine
    return lowpass(s * np.exp(-t / 1.4) * (1 - np.exp(-t / 0.003)), 4000)


def sub_bass(m, dur):
    t = t_axis(dur)
    return np.sin(2 * np.pi * hz(m + 12) * t) * ar_env(t, 0.8, dur - 2.6, 1.8)


def reverb(x, rt60=2.6, wet=0.35):
    t = t_axis(3.5)
    irs = [lowpass(rng.standard_normal(len(t)) * 10 ** (-3 * t / rt60), 5000) for _ in range(2)]
    irs = [ir / np.sqrt(np.sum(ir ** 2)) for ir in irs]
    w = np.stack([fftconvolve(x[i], irs[i])[: x.shape[1]] for i in range(2)])
    return (1 - wet) * x + wet * w


def pad_layer(cutoff, level):
    """One chord cycle of pad, rendered once and reused."""
    cyc = np.zeros((2, int((len(PROG) * CHORD + TAIL) * SR)))
    for k, (_, voicing) in enumerate(PROG):
        dur = CHORD + 2.2
        env = ar_env(t_axis(dur), 1.4, CHORD - 1.4, 2.2)
        for m in voicing:
            add(cyc, k * CHORD, pad_note(m, dur, cutoff) * env * level)
    return cyc


def render(style):
    global rng
    rng = np.random.default_rng(STYLES.index(style) + 7)             # deterministic per style
    buf = np.zeros((2, int((LOOP + TAIL) * SR)))
    pad = {"calm-pad": pad_layer(1500, 0.55), "gentle-pulse": pad_layer(950, 0.4),
           "warm-keys": pad_layer(900, 0.22)}[style]
    for c in range(CYCLES):
        add(buf, c * len(PROG) * CHORD, pad)
        for k, (bass, voicing) in enumerate(PROG):
            t0 = (c * len(PROG) + k) * CHORD
            add(buf, t0, pan(sub_bass(bass, CHORD + 1.8) * 0.22, 0))
            if style == "gentle-pulse":
                notes = [v + 12 for v in voicing]
                seq = [0, 1, 2, 3, 2, 1, 2, 3] if c == 0 else [0, 2, 1, 3, 2, 3, 1, 2]
                for i in range(16):                                  # eighth notes
                    add(buf, t0 + i * BEAT / 2,
                        pan(pluck(notes[seq[i % 8]]) * (0.16 if i % 4 else 0.2), 0.35 if i % 2 else -0.35))
            if style == "warm-keys":
                for b in (0, 3, 4, 6):                               # gentle syncopated comping
                    for j, v in enumerate(voicing):
                        add(buf, t0 + b * BEAT + j * 0.012, pan(epiano(v) * (0.13 if b in (0, 4) else 0.08), -0.3 + 0.2 * j))
                top = voicing[-1] + 12 if c == 0 else voicing[-2] + 12
                add(buf, t0 + 7 * BEAT, pan(epiano(top) * 0.07, 0.25))
    buf = reverb(buf, wet=0.42 if style == "calm-pad" else 0.33)
    tail = buf[:, int(LOOP * SR):]                                   # fold tail into start: seamless loop
    out = buf[:, : int(LOOP * SR)].copy()
    out[:, : tail.shape[1]] += tail
    out = sosfilt(butter(2, 35, "highpass", fs=SR, output="sos"), out, axis=-1)  # remove rumble/DC
    return (out / np.max(np.abs(out)) * 0.7).T


def ensure(style, directory):
    """Path to the cached bed for `style`, synthesising it on first use (~10 s)."""
    path = pathlib.Path(directory) / f"{style}.flac"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[html2mp4] synthesising music bed '{style}' (first use only)", flush=True)
        sf.write(path, render(style), SR, subtype="PCM_24")
    return path


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    for style in STYLES:
        path = out / f"{style}.flac"
        path.unlink(missing_ok=True)
        print("wrote", ensure(style, out))


if __name__ == "__main__":
    main()
