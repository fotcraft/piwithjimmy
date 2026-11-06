"""Accuracy and speed benchmark for the OCR pipeline.

Folder layout (one subfolder per category, any names you like):

    bench/
      greek_print/       page01.jpg  page01.txt  ...
      english_print/     ...
      english_handwriting/
      greek_handwriting/

Each .txt holds the exact text on the photo (the ground truth).

Usage (from the repo root):
    python3 tools/benchmark.py bench/ --out results.csv

Reports, per category and overall:
- accuracy = 1 - CER (character error rate, Levenshtein distance / length),
  after normalising whitespace and case; Greek accents are kept
- median and worst time from image to text
- which engine produced each result (azure_read, vlm_*, local_tesseract)
"""
import argparse
import csv
import os
import statistics
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

IMAGE_EXT = (".jpg", ".jpeg", ".png")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join(text.split())


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(truth: str, hyp: str) -> float:
    t, h = normalise(truth), normalise(hyp)
    if not t:
        return 0.0 if not h else 1.0
    return min(1.0, levenshtein(t, h) / len(t))


def find_samples(root: str):
    for dirpath, _, files in sorted(os.walk(root)):
        for name in sorted(files):
            if name.lower().endswith(IMAGE_EXT):
                img = os.path.join(dirpath, name)
                txt = os.path.splitext(img)[0] + ".txt"
                if os.path.exists(txt):
                    category = os.path.relpath(dirpath, root)
                    yield category, img, txt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="benchmark_results.csv")
    args = parser.parse_args()

    import cv2

    from app.config import load_config
    from app.vision.pipeline import VisionPipeline

    pipeline = VisionPipeline(load_config(args.config))
    rows = []
    for category, img_path, txt_path in find_samples(args.folder):
        image = cv2.imread(img_path)
        with open(txt_path, encoding="utf-8") as fh:
            truth = fh.read()
        start = time.monotonic()
        result = pipeline.process(image, skip_quality=True)
        seconds = time.monotonic() - start
        err = cer(truth, result.text)
        rows.append(
            {
                "category": category,
                "file": os.path.basename(img_path),
                "accuracy_pct": round(100 * (1 - err), 1),
                "seconds": round(seconds, 2),
                "source": result.source or result.status,
                "chars": len(normalise(truth)),
            }
        )
        print(f"{category:24s} {rows[-1]['file']:24s} {rows[-1]['accuracy_pct']:5.1f}%  "
              f"{seconds:5.2f}s  {rows[-1]['source']}")

    if not rows:
        print("No image + .txt pairs found.")
        return 1

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\nSummary (accuracy weighted by characters)")
    print(f"{'category':24s} {'n':>3s} {'accuracy':>9s} {'median s':>9s} {'max s':>7s}")
    groups = sorted({r["category"] for r in rows}) + ["ALL"]
    for g in groups:
        sel = rows if g == "ALL" else [r for r in rows if r["category"] == g]
        chars = sum(r["chars"] for r in sel) or 1
        acc = sum(r["accuracy_pct"] * r["chars"] for r in sel) / chars
        secs = [r["seconds"] for r in sel]
        print(f"{g:24s} {len(sel):3d} {acc:8.1f}% {statistics.median(secs):9.2f} {max(secs):7.2f}")
    print(f"\nPer-file results: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
