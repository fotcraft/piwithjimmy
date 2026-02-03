import argparse
import sys

from app.config import load_config
from app.orchestrator import Orchestrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP Reader (Pi 5 + Coral TPU)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single Scan flow and exit",
    )
    parser.add_argument(
        "--image",
        default="",
        help="Path to an image file to run the pipeline without a camera",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    app = Orchestrator(config)

    if args.image:
        import cv2

        image = cv2.imread(args.image)
        if image is None:
            print(f"Failed to load image: {args.image}")
            return 1
        app.handle_scan_with_image(image)
        app.wait_for_audio()
        return 0

    if args.once:
        app.handle_scan()
        app.wait_for_audio()
        return 0

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
