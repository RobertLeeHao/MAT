#!/usr/bin/env python3
"""The weekly table of models MAT can run on a Mac through Ollama.

  python local_models.py --out ../local/latest.json [--previous ../local/latest.json]

For every family in local.json it reads that family's tags page on ollama.com
and keeps the plain tags (no quantisation or MLX variants): download size,
context window, and whether it reads pictures. Each tag gets the memory a Mac
needs to run it comfortably, and each memory size gets one pick — the first
tag in `prefer` that fits. The app asks this table at onboarding and every
time Settings › Providers opens, and recommends the pick for that Mac.

A family that fails to load keeps last week's rows, marked stale. If nothing
loads at all, nothing is written.
"""
import argparse, datetime, json, math, os, re, sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = re.compile(r":latest$|mlx|-q\d|_k|fp16|bf16|nvfp|mxfp|-int\d|-qat|cloud|-it-|-instruct|-think|-coding|-a\d+b")
ROW = re.compile(
    r'href="/library/(?P<tag>[a-z0-9.\-]+:[a-z0-9.\-]+)"[^>]*>'
    r'.*?<span class="font-mono">\s*[0-9a-f]+\s*</span>\s*•\s*'
    r'(?P<size>[\d.]+)\s*(?P<unit>GB|MB)(?:\s*-\s*[\d.]+\s*GB)?\s*•\s*'
    r'(?P<ctx>[\dKM]+)\s+context window\s*•\s*<span[^>]*>\s*(?P<input>[^•<]*?)\s+input',
    re.S)


def ram_for(gb, buckets):
    """Memory to run it with the OS and a long context alongside: weights × 1.2 + 3 GB."""
    need = gb * 1.2 + 3
    return next((b for b in buckets if b >= need), buckets[-1])


def parse(html, family):
    rows, seen = [], set()
    for m in ROW.finditer(html):
        tag = m.group("tag")
        if not tag.startswith(family + ":") or tag in seen or SKIP.search(tag.lower()):
            continue
        seen.add(tag)
        gb = float(m.group("size")) / (1000 if m.group("unit") == "MB" else 1)
        rows.append({"tag": tag, "gb": round(gb, 1), "context": m.group("ctx"),
                     "vision": "Image" in m.group("input")})
    return rows


def name_of(tag):
    fam, size = tag.split(":", 1)
    fam = re.sub(r"^qwen", "Qwen", fam).replace("gemma", "Gemma ").replace("gpt-oss", "gpt-oss")
    fam = fam.replace("ministral-", "Ministral ").replace("granite", "Granite ").replace("deepseek-r1", "DeepSeek-R1")
    return f"{fam} {size.upper()}".replace("  ", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, "local.json")))
    prev = {}
    if a.previous and os.path.exists(a.previous):
        for m in json.load(open(a.previous)).get("models", []):
            prev.setdefault(m["family"], []).append(m)
    today = datetime.date.today().isoformat()
    models, loaded = [], 0
    for f in cfg["families"]:
        fam = f["family"]
        try:
            r = requests.get(f"https://ollama.com/library/{fam}/tags", timeout=30,
                             headers={"User-Agent": "MAT local-models table (+https://robertleehao.github.io/MAT/)"})
            r.raise_for_status()
            rows = parse(r.text, fam)
            if not rows:
                raise ValueError("no tags parsed")
            loaded += 1
            for x in rows:
                models.append({**x, "family": fam, "maker": f["maker"], "name": name_of(x["tag"]),
                               "ramGB": ram_for(x["gb"], cfg["ramBuckets"]),
                               "tools": f["tools"], "thinking": f["thinking"],
                               "good": f["good"], "read": today})
        except Exception as e:
            print(f"⚠ {fam}: {e} — keeping last week's rows", file=sys.stderr)
            for x in prev.get(fam, []):
                models.append({**x, "stale": True})
    if loaded == 0:
        print("⛔ nothing loaded; not writing", file=sys.stderr)
        sys.exit(1)
    have = {m["tag"]: m for m in models}
    picks = []
    for b in cfg["ramBuckets"]:
        t = next((p for p in cfg["prefer"] if p in have and have[p]["ramGB"] <= b), None)
        if t:
            picks.append({"ramGB": b, "tag": t})
    out = {"version": 1, "date": today, "source": cfg["source"],
           "note": "Sizes are Ollama's download sizes. ramGB is the Mac memory MAT recommends for each (weights × 1.2 + 3 GB). Picks follow a hand-kept preference order, not a benchmark.",
           "picks": picks, "models": sorted(models, key=lambda m: (m["family"], m["gb"]))}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"✅ {len(models)} tags from {loaded}/{len(cfg['families'])} families; picks: " +
          ", ".join(f"{p['ramGB']}GB→{p['tag']}" for p in picks))


if __name__ == "__main__":
    main()
