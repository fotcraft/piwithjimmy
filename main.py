import argparse
import logging
import sys
import threading

from app.config import load_config
from app.hal.buttons import ButtonEvent
from app.orchestrator import Orchestrator
from app.prompts.phrases import PROMPT_PHRASES

KEYMAP = {
    "s": ButtonEvent.SCAN,
    "r": ButtonEvent.REPEAT,
    "+": ButtonEvent.VOL_UP,
    "-": ButtonEvent.VOL_DOWN,
    "l": ButtonEvent.LANG_TOGGLE,
    "h": ButtonEvent.HELP,
    "b": ButtonEvent.LOW_BATTERY,
    "p": ButtonEvent.BATTERY,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Readable: handheld text reader")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--once", action="store_true", help="Run a single Scan and exit")
    parser.add_argument("--image", default="", help="Run the pipeline on an image file (no camera)")
    parser.add_argument(
        "--keys",
        action="store_true",
        help="Simulate buttons from the keyboard: s=scan r=repeat +/-=volume l=language h=help",
    )
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="Synthesise all spoken prompts with Azure once, so they work offline",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def _keyboard_loop(app: Orchestrator) -> None:
    print("Keys: s=scan r=repeat +=vol up -=vol down l=language h=help p=battery b=low battery, Enter after each")
    for line in sys.stdin:
        for ch in line.strip():
            event = KEYMAP.get(ch)
            if event:
                app.buttons.simulate(event)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    config = load_config(args.config)
    app = Orchestrator(config)

    try:
        if args.warm_cache:
            for lang, phrases in PROMPT_PHRASES.items():
                for pid, text in phrases.items():
                    if "{" in text:
                        continue
                    path = app.audio._azure_wav(text, lang)
                    print(f"{lang}/{pid}: {'ok' if path else 'FAILED'}")
            return 0

        if args.image:
            import cv2

            image = cv2.imread(args.image)
            if image is None:
                print(f"Failed to load image: {args.image}")
                return 1
            result = app.handle_scan_with_image(image)
            if result:
                print(f"[{result.source} conf={result.confidence:.0f}] {result.text}")
            app.wait_for_audio()
            return 0

        if args.once:
            app.handle_scan()
            app.wait_for_audio()
            return 0

        if args.keys:
            threading.Thread(target=_keyboard_loop, args=(app,), daemon=True).start()
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        app.close()


if __name__ == "__main__":
    sys.exit(main())
