"""API loop: rolling narration with a bounded, text-only context window."""

import base64
import datetime as dt
import json
from pathlib import Path

MODEL = "claude-sonnet-5"
MAX_EXCHANGES = 10  # user+assistant pairs kept in context

SYSTEM = (
    "Tu racontes en direct ce qui se passe dans une pièce, pour un foyer dont "
    "les habitants ont des troubles de la mémoire. À chaque nouvelle image, "
    "décris en UNE phrase courte en français ce qui a changé ou l'événement "
    "notable (quelqu'un entre, s'assoit, pose un objet...). Ne redécris jamais "
    "la scène statique déjà décrite. Si rien n'a changé, réponds exactement : RAS"
)

DIM = "\033[2m"
RESET = "\033[0m"


def log_path(logs_dir: Path, day: dt.date | None = None) -> Path:
    day = day or dt.date.today()
    return logs_dir / f"narration-{day.isoformat()}.jsonl"


def append_jsonl(path: Path, ts: str, description: str, event: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"ts": ts, "description": description, "event": event},
                           ensure_ascii=False) + "\n")


def describe_frame(client, messages: list, frame: bytes, media_type: str, ts: str) -> str:
    """Send the current frame with the rolling text context; return the description.

    Mutates `messages`: appends this exchange, replaces the image turn by its
    text placeholder (so only the CURRENT frame is ever sent as an image), and
    trims to the last MAX_EXCHANGES exchanges.
    """
    messages.append({
        "role": "user",
        "content": [
            {"type": "image",
             "source": {"type": "base64", "media_type": media_type,
                        "data": base64.standard_b64encode(frame).decode()}},
            {"type": "text", "text": f"Nouvelle image ({ts}). Que s'est-il passé ?"},
        ],
    })
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM, messages=messages,
    )
    description = "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()

    # Replace the image turn with text so the context stays cheap and text-only.
    messages[-1] = {"role": "user", "content": f"[image à {ts}]"}
    messages.append({"role": "assistant", "content": description or "RAS"})
    del messages[:-2 * MAX_EXCHANGES]
    return description or "RAS"


def narrate(client, source, interval: float, logs_dir: Path,
            max_frames: int | None = None, sleep=None, out=print) -> int:
    """Main loop. Returns the number of frames narrated."""
    import time
    sleep = sleep or time.sleep
    messages: list = []
    n = 0
    while max_frames is None or n < max_frames:
        got = source()
        if got is None:
            break
        frame, media_type = got
        ts = dt.datetime.now().isoformat(timespec="seconds")
        description = describe_frame(client, messages, frame, media_type, ts)
        is_ras = description.strip().upper() == "RAS"
        append_jsonl(log_path(logs_dir), ts, description, event=not is_ras)
        if is_ras:
            out(f"{DIM}[{ts}] · (rien de nouveau){RESET}")
        else:
            out(f"[{ts}] {description}")
        n += 1
        if max_frames is not None and n >= max_frames:
            break
        sleep(interval)
    return n


def recap(client, logs_dir: Path, out=print) -> str:
    """Summarize today's narration jsonl in one API call."""
    path = log_path(logs_dir)
    if not path.exists():
        out(f"Aucune narration aujourd'hui ({path})")
        return ""
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    events = [f"{e['ts']}  {e['description']}" for e in lines]
    response = client.messages.create(
        model=MODEL, max_tokens=2000,
        system=("Tu résumes la journée d'une pièce pour un foyer dont les habitants "
                "ont des troubles de la mémoire. Fais un résumé chronologique clair "
                "et bienveillant en français, en quelques paragraphes courts."),
        messages=[{"role": "user",
                   "content": "Voici la narration de la journée :\n" + "\n".join(events)}],
    )
    text = "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    out(text)
    return text
