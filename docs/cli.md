# Command-line reference

Installing the project provides three commands. Activate the environment first, or call them through `.venv/bin/`:

```bash
source .venv/bin/activate
```

| Command | Purpose |
|---|---|
| `html2mp4` | Convert a module to MP4 |
| `html2mp4-studio` | Start the Studio web app |
| `html2mp4-music` | Write the built-in music beds to a folder |

## `html2mp4`

```
html2mp4 MODULE.html [options]
```

Writes `MODULE.mp4` next to the input, with `MODULE.srt` and `MODULE.vtt` caption files.

| Option | Default | Description |
|---|---|---|
| `-o, --out PATH` | next to the input | Output `.mp4` path. Caption files are written alongside it. |
| `--voice ID` | `af_heart` | Narrator voice. See [Voices](#voices). |
| `--speed X` | `0.90` | Speaking rate. The Studio offers 0.85 (relaxed), 0.90 (natural) and 1.0 (brisk). |
| `--music NAME\|PATH\|none` | `gentle-pulse` | A built-in bed (`gentle-pulse`, `calm-pad`, `warm-keys`), any audio file, or `none`. |
| `--music-volume LEVEL` | `balanced` | `subtle`, `balanced` or `present`, or a number: how many dB the music sits below the voice while it speaks. |
| `--quality Q` | `1440p` | `1440p` (2560×1440) or `1080p` (1920×1080). |
| `--preview SECONDS` | | Render only the opening SECONDS, with a faster encode, to audition settings. |
| `--scenes N` | all | Render only the first N slides. |
| `--workers N` | half the CPU cores | Parallel frame renderers. |

Examples:

```bash
html2mp4 onboarding.html
html2mp4 onboarding.html --voice am_michael --speed 1.0 --music none
html2mp4 onboarding.html --music ~/Music/licensed-track.mp3 --music-volume subtle
html2mp4 onboarding.html --preview 10 -o /tmp/try.mp4
```

The command exits with status 0 on success. If the module can't be converted, it prints `[html2mp4] error:` with the
reason and exits with a non-zero status.

### Voices

| ID | Voice |
|---|---|
| `af_heart` | Heart: warm and friendly, US female (default) |
| `af_bella` | Bella: bright and upbeat, US female |
| `am_michael` | Michael: calm and assured, US male |
| `am_fenrir` | Fenrir: deep and steady, US male |
| `bf_emma` | Emma: clear and polished, UK female |
| `bm_george` | George: measured and classic, UK male |

These are the voices offered in the Studio. The command line accepts any other
[Kokoro voice](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) whose ID starts with `a` (American
English) or `b` (British English).

### Music volume

The music follows the narration: it sits below the voice while someone is speaking and rises by 6 dB in pauses,
gliding down in 0.3 s and back up in 0.9 s. It fades in over the first 2 seconds and out with the video.

| Level | Below the voice while speaking | In pauses |
|---|---|---|
| `subtle` | 17 dB | 11 dB |
| `balanced` | 12 dB | 6 dB |
| `present` | 8 dB | 2 dB |

## `html2mp4-studio`

```
html2mp4-studio
```

Starts the Studio on `http://127.0.0.1:8765`, or the next free port, and opens it in the default browser. The
server only listens on the local machine. Press Ctrl+C in its window to stop it. `./studio.sh` and
**Open Studio.command** run this command.

## `html2mp4-music`

```
html2mp4-music [DIR]
```

Writes the built-in music beds (`gentle-pulse.flac`, `calm-pad.flac`, `warm-keys.flac`) to `DIR`, or to the current
directory. Each is a 48-second seamless loop at 48 kHz, synthesised in code. The output is deterministic and free to use.

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `HTML2MP4_CACHE` | `~/.cache/html2mp4` | Where narration clips, music beds, rendered pictures and Studio state are kept. Safe to delete. |
| `HTML2MP4_OUTPUT` | `~/Downloads/Narrated Videos` | Where the Studio saves finished videos. |
| `HTML2MP4_NO_BROWSER` | unset | If set, the Studio doesn't open a browser window on start. |

## Using it from Python

```python
from html2mp4.cli import convert, ConversionError

result = convert("module.html", "out/module.mp4", voice="bf_emma", music="none", quality="1080p",
                 progress=lambda fraction, label: print(f"{fraction:.0%} {label}"))
print(result["mp4"], result["duration"])
```

`convert` raises `ConversionError` with a readable message for invalid input. It raises `Cancelled` if the `cancel`
event it was given is set.
