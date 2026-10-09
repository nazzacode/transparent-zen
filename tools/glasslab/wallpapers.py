"""glasslab wallpapers: test backdrops + contrast bounds from YOUR wallpapers (images or videos), blurred like the
compositor blurs what's behind a window. Writes ~/.cache/glasslab/backdrops/{*.png,bounds.json}; the suite reads it."""
import json, subprocess, tempfile
from pathlib import Path

from PIL import Image, ImageFilter

from .suite import BACKDROPS

IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".mov", ".mp4", ".mkv", ".webm"}


def frame(path, tmp):
    if path.suffix.lower() in IMG:
        return Image.open(path)
    out = Path(tmp) / f"{path.stem}.png"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "20", "-i", str(path), "-frames:v", "1", "-vf", "scale=1400:-2", str(out)], check=True)
    return Image.open(out)


def main(paths, blur=22, sheet=5):
    files = sorted({f for p in map(Path, paths) for f in (p.iterdir() if p.is_dir() else [p]) if f.suffix.lower() in IMG | VID})
    if not files:
        raise SystemExit("glasslab wallpapers: no images/videos found")
    BACKDROPS.mkdir(parents=True, exist_ok=True)
    stats = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            try:
                im = frame(f, tmp).convert("RGB").resize((1400, 1000)).filter(ImageFilter.GaussianBlur(blur))
            except Exception as e:  # noqa: BLE001 — skip unreadable files, keep going
                print(f"  skip {f.name}: {e}")
                continue
            im.save(BACKDROPS / f"{f.stem}.png")
            lum = sorted(im.convert("L").getdata())
            stats.append((f.stem, lum[len(lum) // 2], lum[int(.05 * (len(lum) - 1))], lum[int(.95 * (len(lum) - 1))]))
    stats.sort(key=lambda s: s[1])
    lo, hi = min(s[2] for s in stats), max(s[3] for s in stats)
    picks = [stats[round(i * (len(stats) - 1) / max(1, sheet - 1))][0] for i in range(min(sheet, len(stats)))]
    mid = stats[len(stats) // 2][0]                      # first = median brightness: the representative gallery backdrop
    picks = [mid] + [p for p in picks if p != mid]
    (BACKDROPS / "bounds.json").write_text(json.dumps({"bounds": [[lo] * 3, [hi] * 3], "sheet": list(dict.fromkeys(picks)), "blur": blur,
                                                        "wallpapers": [{"name": n, "median": m, "p5": a, "p95": b} for n, m, a, b in stats]}, indent=1))
    print(f"{len(stats)} backdrops → {BACKDROPS}\ncontrast bounds: darkest {lo}, brightest {hi} (p5/p95 over all)\nsheet: {', '.join(picks)}")
