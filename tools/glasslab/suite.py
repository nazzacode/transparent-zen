"""glasslab test: readability + unity matrix for every screen in screens.json.

Per screen × glass mode × slider alpha:
  - captures over pure black and pure white → exact per-pixel colour + alpha (CSP-proof), composited offline onto
    blurred wallpapers (backdrops) → contact sheets
  - text probe: every visible text run, APCA through its real paint stack over the backdrop bounds (darkest / brightest
    blurred-wallpaper patch). Target per run: size floor (75 body · 60 labels/controls · 45 large), relaxed to the site's
    own native contrast ×0.9 where the native design is already below it → glass never reads worse than the site.
  - unity: surfaces must be glass.css tiers; neutral text must be a shared foreground.
Exemptions (reported, not scored): text on site data colours / images / accent fills — void if glass changed its colour.
"""
import asyncio, json, os, re, time
from pathlib import Path

import numpy as np
from PIL import Image

from . import lab

HERE = Path(__file__).parent
ALPHAS = [0.1, 0.45, 0.9]          # popup slider extremes + default
DEFAULT_ALPHA = 0.45
MODES = ["dark", "light"]
TARGETS = {"contrast": 0.9, "surface": 0.9, "text": 0.85, "exempt_max": 0.1}
REGRESSION = 0.03                   # baseline compare: a metric dropping more than this fails
BACKDROPS = Path(os.environ.get("GLASSLAB_BACKDROPS", Path.home() / ".cache/glasslab/backdrops"))
DEFAULT_BOUNDS = [[0, 0, 0], [222, 222, 222]]   # measured over 22 live wallpapers (p5 / p95, blurred) on 2026-10-09


def backdrops():
    """bounds + wallpaper images from `glasslab wallpapers`; synthetic fallback so the suite always runs"""
    meta = BACKDROPS / "bounds.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        return m["bounds"], {w: Image.open(BACKDROPS / f"{w}.png") for w in m["sheet"]}
    sky = Image.linear_gradient("L").resize((1400, 1000)).convert("RGB")
    return DEFAULT_BOUNDS, {"synthetic-day": Image.eval(sky, lambda v: 120 + v // 3), "synthetic-night": Image.eval(sky, lambda v: v // 6)}


def load_screens(filt=""):
    data = json.loads((HERE / "screens.json").read_text())
    return [s for s in data["screens"] if re.search(filt, s["id"])]


def rkey(r):
    """identity of a text run across native/glass renders: selector + text + position (layout is identical)"""
    return (r["sel"], r["t"], r.get("x", 0) // 4, r.get("y", 0) // 4)


def neutral_text_conformance(runs, fgs, tol=10):
    """share of neutral text chars whose colour is a glass foreground (saturated text = accent/status, ignored)"""
    ok = tot = 0
    foreign = {}
    for r in runs:
        c = [float(x) for x in re.findall(r"[\d.]+", r["fg"])[:3]]
        if len(c) < 3 or max(c) - min(c) > 24:
            continue
        tot += r["n"]
        if any(f and all(abs(c[i] - f[i]) <= tol for i in range(3)) for f in fgs):
            ok += r["n"]
        else:
            k = f"{r['fg']} {r['sel']}"
            foreign[k] = foreign.get(k, 0) + r["n"]
    return (ok / tot if tot else 1.0), sorted(foreign.items(), key=lambda x: -x[1])[:6]


def score(runs, native, fgs, unity):
    """split exempt runs, set per-run targets, compute contrast pass per bound + unity"""
    def exempt(r):
        nv = native.get(rkey(r))
        return (r.get("chip") or r.get("img")) and nv is not None and nv[1] == r["fg"]
    ex = [r for r in runs if exempt(r)]
    sc = [r for r in runs if not exempt(r)]
    for r in sc:
        nv = native.get(rkey(r))
        r["native"] = nv and nv[0]
        r["target"] = r["need"] if nv is None else min(r["need"], nv[0] * 0.9)
    tot = sum(r["n"] for r in sc) or 1
    nb = len(sc[0]["cr"]) if sc else 0
    contrast = [sum(r["n"] for r in sc if r["cr"][k] >= r["target"]) / tot for k in range(nb)] or [1.0]
    text, text_foreign = neutral_text_conformance(sc, fgs)
    failing = {}
    for r in sc:
        if min(r["cr"]) < r["target"]:
            g = failing.setdefault(r["sel"], {"sel": r["sel"], "chars": 0, "lc": r["cr"], "target": round(r["target"]), "fg": r["fg"], "t": r["t"]})
            g["chars"] += r["n"]
    img_exempt = sum(r["n"] for r in ex if r.get("img") and not r.get("chip")) / max(1, sum(r["n"] for r in runs))
    return {"texts": len(sc), "exempt": len(ex), "exempt_img_share": round(img_exempt, 3), "contrast": [round(v, 3) for v in contrast],
            "surface": round(unity.get("surface", 0), 3), "text": round(text, 3), "tiers": unity.get("tiers", {}),
            "surface_foreign": unity.get("foreign", []), "text_foreign": text_foreign,
            "failing": sorted(failing.values(), key=lambda g: -g["chars"])[:10]}


def verdict(m):
    return (min(m["contrast"]) >= TARGETS["contrast"] and m["surface"] >= TARGETS["surface"]
            and m["text"] >= TARGETS["text"] and m["exempt_img_share"] <= TARGETS["exempt_max"])


async def run_screens(xpi, out, screens, bounds):
    results = []
    async with lab.session(xpi, out / "zen.log") as pg:
        for sc in screens:
            print(f"· {sc['id']}", flush=True)
            await pg.goto(sc["url"], sc.get("settle", 7), sc.get("act"))
            await pg.detach_styles()
            (await pg.shot()).save(out / "shots" / f"{sc['id']}.native.png")
            native = {rkey(r): (min(r["cr"]), r["fg"]) for r in (await pg.probe("text", bounds, [0, 0, 0, 0]) or [])}
            await pg.attach_styles()
            for mode in sc.get("modes", MODES):
                for a in ALPHAS:
                    await pg.glass(mode, a)
                    key = f"{sc['id']}.{mode}.{int(a * 100)}"
                    (await pg.shot("#000")).save(out / "raw" / f"{key}.black.png")
                    (await pg.shot("#fff")).save(out / "raw" / f"{key}.white.png")
                    await pg.clear_backdrop()
                    runs = await pg.probe("text", bounds, [0, 0, 0, 0]) or []
                    unity = await pg.probe("unity") or {}
                    m = score(runs, native, unity.get("fgs", []), unity)
                    m.update(key=key, screen=sc["id"], mode=mode, alpha=a, ok=verdict(m))
                    results.append(m)
                    print(f"  {key:30s} contrast {min(m['contrast']):4.0%}  surface {m['surface']:4.0%}  text {m['text']:4.0%}"
                          f"  {'ok' if m['ok'] else 'FAIL'}", flush=True)
    return results


def composite(black, white, wall):
    """exact: out = B + (1-α)·wall, α = 1 - (W-B)/255 (mean over channels)"""
    B = np.asarray(black.convert("RGB"), dtype=np.float32)
    Wt = np.asarray(white.convert("RGB"), dtype=np.float32)
    alpha = 1 - (Wt - B).mean(axis=2, keepdims=True) / 255
    bg = np.asarray(wall.convert("RGB").resize(black.size), dtype=np.float32)
    return Image.fromarray(np.clip(B + (1 - alpha) * bg, 0, 255).astype("uint8"))


def sheets(results, out, walls):
    first = next(iter(walls.values()))
    for scr in dict.fromkeys(r["screen"] for r in results):
        modes = [m for m in MODES if (out / "raw" / f"{scr}.{m}.{int(ALPHAS[0] * 100)}.black.png").exists()]
        rows = []
        for mode in modes:
            row = []
            for a in ALPHAS:
                key = f"{scr}.{mode}.{int(a * 100)}"
                img = composite(Image.open(out / "raw" / f"{key}.black.png"), Image.open(out / "raw" / f"{key}.white.png"), first)
                img.save(out / "shots" / f"{key}.png")
                row.append(img)
            rows.append(row)
        for mode in modes:
            key = f"{scr}.{mode}.{int(DEFAULT_ALPHA * 100)}"
            blk, wht = Image.open(out / "raw" / f"{key}.black.png"), Image.open(out / "raw" / f"{key}.white.png")
            rows.append([composite(blk, wht, w) for w in walls.values()])
        tw, th = 700, 500
        sheet = Image.new("RGB", (max(map(len, rows)) * tw, len(rows) * th), (40, 40, 40))
        for y, row in enumerate(rows):
            for x, im in enumerate(row):
                sheet.paste(im.resize((tw, th)), (x * tw, y * th))
        sheet.save(out / f"sheet-{scr}.jpg", quality=85)


def summary_md(results):
    lines = ["| screen | mode | α | texts | contrast dark bg | contrast bright bg | surface | text | ok | worst |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        w = r["failing"][0] if r["failing"] else None
        c = r["contrast"] + r["contrast"][-1:]
        lines.append(f"| {r['screen']} | {r['mode']} | {int(r['alpha'] * 100)} | {r['texts']} | {c[0]:.0%} | {c[1]:.0%} | "
                     f"{r['surface']:.0%} | {r['text']:.0%} | {'✓' if r['ok'] else '✗'} | "
                     + (f"`{w['sel']}` Lc {min(w['lc'])} (target {w['target']})" if w else "") + " |")
    return "\n".join(lines) + "\n"


def baseline_numbers(results):
    """numbers only (no page text) → safe to commit"""
    return {r["key"]: {"contrast": min(r["contrast"]), "surface": r["surface"], "text": r["text"], "ok": r["ok"]} for r in results}


def compare(results, baseline):
    regs = []
    for k, now in baseline_numbers(results).items():
        was = baseline.get(k)
        if not was:
            continue
        for m in ("contrast", "surface", "text"):
            if now[m] < was[m] - REGRESSION:
                regs.append(f"{k} {m} {was[m]:.0%} → {now[m]:.0%}")
    return regs


def main(xpi, filt="", out=None, save_baseline=False, compare_baseline=False):
    screens = load_screens(filt)
    if not screens:
        raise SystemExit(f"glasslab: no screens match {filt!r}")
    out = Path(out or Path.home() / ".cache/glasslab/runs" / time.strftime("%Y%m%d-%H%M%S"))
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    bounds, walls = backdrops()
    results = asyncio.run(run_screens(xpi, out, screens, bounds))
    sheets(results, out, walls)
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "summary.md").write_text(summary_md(results))
    fails = [r["key"] for r in results if r["alpha"] == DEFAULT_ALPHA and not r["ok"]]
    extremes = [r["key"] for r in results if r["alpha"] != DEFAULT_ALPHA and not r["ok"]]
    bl = HERE / "baseline.json"
    regs = compare(results, json.loads(bl.read_text())) if compare_baseline and bl.exists() else []
    if save_baseline:
        merged = json.loads(bl.read_text()) if bl.exists() else {}
        merged.update(baseline_numbers(results))
        bl.write_text(json.dumps(dict(sorted(merged.items())), indent=1) + "\n")
    print(f"\nrun: {out}\nfails at default α: {fails or 'none'}\nfails at slider extremes: {extremes or 'none'}"
          + (f"\nregressions vs baseline: {regs or 'none'}" if compare_baseline else ""))
    return 1 if fails or regs else 0
