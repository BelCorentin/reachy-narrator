"""Entry point: python -m narrator.main [--interval N] [--source robot|webcam|dir:<path>] [--recap] [--max-frames N]"""

import argparse
import os
import sys
from pathlib import Path

from narrator import capture, narrate

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live room narrator for Reachy Mini")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="seconds between frames (default 5)")
    parser.add_argument("--source", default="robot",
                        help="robot | webcam | dir:<path> (default robot)")
    parser.add_argument("--recap", action="store_true",
                        help="summarize today's narration log and exit")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="stop after N frames (default: run forever)")
    args = parser.parse_args(argv)

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Export it and retry:\n"
              "  export ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
        return 1

    import anthropic
    client = anthropic.Anthropic()

    if args.recap:
        narrate.recap(client, LOGS_DIR)
        return 0

    source = capture.make_source(args.source)
    try:
        n = narrate.narrate(client, source, args.interval, LOGS_DIR,
                            max_frames=args.max_frames)
    except KeyboardInterrupt:
        print("\narrêt.")
        return 0
    print(f"fin ({n} images).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
