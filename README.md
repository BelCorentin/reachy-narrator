# reachy-narrator

Live environment narrator for a Reachy Mini robot: grabs a camera frame every N
seconds, sends it to the Anthropic API (`claude-sonnet-5`, vision), and prints a
rolling French narration of what is happening in the room. The model keeps
context between frames, so it narrates **changes and events** ("quelqu'un entre",
"il s'assoit"), not repeated static scene dumps. Everything is appended to
`logs/narration-<date>.jsonl`; a `--recap` mode summarizes the day in one call.

Built for a memory-impaired household: concise one-liners, `RAS` when nothing
changed (logged, printed as a dim heartbeat).

## Setup

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python --prerelease=allow \
    'reachy-mini>=1.10.0rc2' anthropic pillow opencv-python-headless
export ANTHROPIC_API_KEY=sk-ant-...
```

`reachy-mini` needs system gstreamer/cairo dev libs (pycairo builds from source).

## Usage

```bash
./run.sh                          # robot camera, 1 frame / 5 s
./run.sh --interval 10            # slower cadence
./run.sh --source webcam          # laptop webcam (no robot needed)
./run.sh --source dir:tests/imgs  # iterate a directory of images
./run.sh --recap                  # summarize today's narration log
./run.sh --max-frames 20          # stop after N frames
```

Output goes to the terminal and to `logs/run-<stamp>.log` (`logs/latest.log`
symlink). Narration data: `logs/narration-YYYY-MM-DD.jsonl`, one
`{"ts", "description", "event"}` object per line (`event: false` = RAS).

## Robot gotchas (hard-won, do not remove)

1. **Daemon 1.8.3 reports its hotspot IP (10.42.0.1) as `wlan_ip`**, so the SDK
   dials WebRTC signalling on an unroutable address and times out. Workaround:
   `narrator/capture.py` monkeypatches `MediaManager.__init__` to override the
   `signalling_host` kwarg from `REACHY_SIGNALLING_HOST` (exported by `run.sh`
   as the robot's real IP) before constructing `ReachyMini`.
2. **The signalling server (:8443) only runs after
   `POST http://<robot>:8000/api/media/acquire`** — `run.sh` preflights it with
   curl. The robot is resolved via `REACHY_HOST` env or mDNS
   (`getent hosts reachy-mini.local`).

## Context strategy

Only the **current** frame is sent as an image. After each API call the image
turn is replaced by a text placeholder (`[image à <ts>]`) and the window is
trimmed to the last 10 exchanges, so context stays cheap and text-only while the
model still knows what it already narrated.

## Tests

No pytest, no network (Anthropic client stubbed):

```bash
.venv/bin/python tests/test_narrator.py
```
