"""Standalone tests (no pytest, no network): .venv/bin/python tests/test_narrator.py"""

import copy
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from narrator import capture, narrate  # noqa: E402

PASS = 0


def check(name, cond, detail=""):
    global PASS
    if not cond:
        print(f"FAIL: {name} {detail}")
        sys.exit(1)
    print(f"ok: {name}")
    PASS += 1


class StubClient:
    """Mimics anthropic.Anthropic().messages.create; records every request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))  # snapshot: caller mutates messages after
        text = self.replies.pop(0) if self.replies else "RAS"
        block = SimpleNamespace(type="text", text=text)
        return SimpleNamespace(content=[block])


def make_images(d: Path, n=3):
    from PIL import Image, ImageDraw
    d.mkdir(parents=True, exist_ok=True)
    colors = ["red", "green", "blue", "orange", "purple"]
    for i in range(n):
        img = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(img)
        draw.ellipse([8 + 4 * i, 8, 40 + 4 * i, 40], fill=colors[i % len(colors)])
        img.save(d / f"frame{i:02d}.jpg")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="narrator-test-"))
    imgs = tmp / "imgs"
    imgs.mkdir()
    make_images(imgs, 3)
    logs = tmp / "logs"

    # 1. dir-source iterates all images then returns None
    src = capture.make_source(f"dir:{imgs}")
    frames = []
    while (got := src()) is not None:
        frames.append(got)
    check("dir source yields 3 frames then None", len(frames) == 3)
    check("dir source detects jpeg media type",
          all(mt == "image/jpeg" for _, mt in frames))
    check("dir source frames are jpeg bytes",
          all(data[:2] == b"\xff\xd8" for data, _ in frames))

    # 2. context window: image turns replaced by text, window bounded
    n_frames = narrate.MAX_EXCHANGES + 5
    make_images(imgs2 := tmp / "imgs2", 1)
    frame = (imgs2 / "frame00.jpg").read_bytes()
    client = StubClient([f"événement {i}" for i in range(n_frames)])
    messages = []
    for i in range(n_frames):
        narrate.describe_frame(client, messages, frame, "image/jpeg", f"t{i}")
    check("context bounded to 2*MAX_EXCHANGES",
          len(messages) <= 2 * narrate.MAX_EXCHANGES, f"len={len(messages)}")
    check("no image blocks remain in retained context",
          all(isinstance(m["content"], str) for m in messages))
    # every request sent exactly ONE image block (the current frame)
    for req in client.requests:
        n_img = sum(1 for m in req["messages"] if not isinstance(m["content"], str)
                    for b in m["content"] if b.get("type") == "image")
        check_ok = n_img == 1
        if not check_ok:
            check("exactly one image per request", False, f"got {n_img}")
    check("exactly one image per request (all requests)", True)
    check("assistant replies kept as text context",
          messages[-1] == {"role": "assistant",
                           "content": f"événement {n_frames - 1}"})

    # 3+4. full loop: RAS handling + jsonl lines written
    src = capture.make_source(f"dir:{imgs}")
    client = StubClient(["quelqu'un entre", "RAS", "il s'assoit"])
    printed = []
    n = narrate.narrate(client, src, interval=0, logs_dir=logs,
                        sleep=lambda s: None, out=printed.append)
    check("narrate processed 3 frames", n == 3)
    lines = [json.loads(line) for line in
             narrate.log_path(logs, dt.date.today()).read_text().splitlines()]
    check("3 jsonl lines written", len(lines) == 3)
    check("jsonl has ts/description/event keys",
          all(set(e) == {"ts", "description", "event"} for e in lines))
    check("RAS logged with event=False",
          lines[1]["description"] == "RAS" and lines[1]["event"] is False)
    check("events flagged event=True", lines[0]["event"] and lines[2]["event"])
    check("RAS printed as dim heartbeat, not narration",
          "RAS" not in printed[1] and "rien de nouveau" in printed[1])
    check("real events printed with timestamp",
          "quelqu'un entre" in printed[0] and printed[0].startswith("["))

    # recap reads the jsonl and makes one API call
    client = StubClient(["Résumé de la journée."])
    text = narrate.recap(client, logs, out=lambda s: None)
    check("recap returns summary text", text == "Résumé de la journée.")
    check("recap sends events to the API",
          "quelqu'un entre" in client.requests[0]["messages"][0]["content"])

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
