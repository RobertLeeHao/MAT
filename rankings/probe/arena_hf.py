#!/usr/bin/env python3
"""Arena's own public data: lmarena-ai/leaderboard-dataset on Hugging Face (CC BY 4.0).

For every subset we need, read the `latest` split and report:
  - when it was published (leaderboard_publish_date)
  - which categories it has
  - which of our models it names, and under what names
  - for the boards we copied by hand on Oct 14, whether its ratings agree

Writes out/arena_hf.json, out/arena_hf.md (also the job summary) and the
`latest` rows of each subset as out/arena/<subset>.csv for writing the parser.
"""
import io, json, os, re, time
import requests
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(os.path.join(OUT, "arena"), exist_ok=True)
DS = "lmarena-ai/leaderboard-dataset"
UA = {"User-Agent": "MAT-rankings-probe/0.2 (+https://github.com/RobertLeeHao/MAT)"}
SUBSETS = ["text_style_control", "text", "vision_style_control", "search_style_control", "document_style_control",
           "webdev", "text_to_image", "image_edit", "agent"]
# What we copied from arena.ai on Oct 14 (bench.json): subset, category, model, rating
HAND = json.load(open(os.path.join(HERE, "arena_hand.json")))
OURS = json.load(open(os.path.join(HERE, "our_models.json")))  # display name -> slug stem, e.g. "claude-opus-5.5"

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def parquet_urls():
    r = requests.get(f"https://datasets-server.huggingface.co/parquet?dataset={DS}", headers=UA, timeout=60)
    r.raise_for_status()
    files = r.json()["parquet_files"]
    by = {}
    for f in files:
        by.setdefault((f["config"], f["split"]), []).append(f["url"])
    return by

def load(urls):
    frames = []
    for u in urls:
        b = requests.get(u, headers=UA, timeout=120).content
        frames.append(pd.read_parquet(io.BytesIO(b)))
    return pd.concat(frames, ignore_index=True)

def main():
    report = dict(ran=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), subsets={})
    try:
        urls = parquet_urls()
    except Exception as e:
        report["error"] = repr(e)[:400]
        json.dump(report, open(os.path.join(OUT, "arena_hf.json"), "w"), indent=1)
        print(report); return
    report["configs_available"] = sorted({c for c, _ in urls})
    for sub in SUBSETS:
        r = {}
        try:
            df = load(urls[(sub, "latest")])
            df.to_csv(os.path.join(OUT, "arena", sub + ".csv"), index=False)
            r["rows"] = len(df)
            r["publish_dates"] = sorted({str(d)[:10] for d in df["leaderboard_publish_date"].unique()})
            r["categories"] = sorted(df["category"].unique().tolist())
            names = df["model_name"].astype(str).unique().tolist()
            hits = {}
            stems = {d: norm(st) for d, st in OURS.items()}
            def mine(n, k):
                nn = norm(n)
                return nn.startswith(k) and not any(k2 != k and k2.startswith(k) and nn.startswith(k2) for k2 in stems.values())
            for disp, stem in OURS.items():
                k = norm(stem)
                found = [n for n in names if mine(n, k)]
                if found:
                    hits[disp] = found[:6]
            r["our_models_found"] = len(hits)
            r["our_models_missing"] = sorted(set(OURS) - set(hits))
            r["name_examples"] = hits
            # compare with what the arena.ai pages showed on Oct 14
            val = "rating" if "rating" in df.columns else "score"
            checks = []
            for h in [h for h in HAND if h["subset"] == sub]:
                cat = next((c for c in h["category"] if c in r["categories"]), None)
                if cat is None:
                    checks.append(dict(category=cat, model=h["model"], hand=h["value"], hf=None, match=False, note="category not found")); continue
                d = df[df["category"] == cat]
                k = norm(OURS.get(h["model"], h["model"]))
                m = d[d["model_name"].map(lambda n: mine(n, k))]
                got = sorted(m[val].round(1).tolist(), reverse=True)[:4]
                checks.append(dict(category=cat, model=h["model"], hand=h["value"], hf=got,
                                   match=any(abs(g - h["value"]) <= max(2, abs(h["value"]) * 0.002) for g in got)))
            r["checks"] = checks
        except Exception as e:
            r["error"] = repr(e)[:400]
        report["subsets"][sub] = r
        print(sub, {k: v for k, v in r.items() if k in ("rows", "publish_dates", "our_models_found", "error")})
    json.dump(report, open(os.path.join(OUT, "arena_hf.json"), "w"), indent=1, ensure_ascii=False)
    lines = ["# Arena public dataset probe", "", f"Configs on Hugging Face: {', '.join(report.get('configs_available', []))}", "",
             "| subset | latest published | rows | categories | our models found | hand-copied values that match |", "|---|---|---|---|---|---|"]
    for sub, r in report["subsets"].items():
        if "error" in r:
            lines.append(f"| {sub} | error: {r['error'][:80]} | | | | |"); continue
        ok = sum(c["match"] for c in r["checks"]); n = len(r["checks"])
        lines.append(f"| {sub} | {', '.join(r['publish_dates'])} | {r['rows']} | {len(r['categories'])} | {r['our_models_found']}/{len(OURS)} | {ok}/{n} |")
    md = "\n".join(lines)
    open(os.path.join(OUT, "arena_hf.md"), "w").write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n" + md + "\n")

if __name__ == "__main__":
    main()
