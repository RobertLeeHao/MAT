#!/usr/bin/env python3
"""The weekly table of models MAT can reach through Ollama — on the Mac, or in
Ollama's cloud.

  python local_models.py --out ../local/latest.json [--previous ../local/latest.json] [--changes ../local/changes/<date>.md]

1. Families. The ones in local.json (kept by hand), plus any family found on
   ollama.com's library pages (popular and newest) that holds a conversation
   (tools or thinking; not embedding or decision models), is used (≥ minPulls)
   and was updated within the last year. Found families stay in the table on
   later weeks even if they drop off those pages.
2. Tags. For every family, its tags page: plain local tags (download size,
   context, pictures) and cloud tags (`:cloud`, `<size>-cloud`: usage level,
   context, pictures).
3. Picks. One per Mac memory size: the first tag in `prefer` that fits.
   Only local tags, only from `prefer` — a family found this week is listed,
   never recommended, until someone puts it in `prefer`.

A family that fails to load keeps last week's rows, marked stale. If nothing
loads at all, nothing is written.
"""
import argparse, datetime, json, os, re, sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "MAT local-models table (+https://robertleehao.github.io/MAT/)"}
SKIP_LOCAL = re.compile(r":latest$|mlx|-q\d|_k|fp16|bf16|nvfp|mxfp|-int\d|-qat|-it-|-instruct|-think|-coding|-a\d+b")
ROW = re.compile(
    r'href="/library/(?P<tag>[a-z0-9.\-_]+:[a-z0-9.\-_]+)"[^>]*>'
    r'.*?<span class="font-mono">\s*[0-9a-f]+\s*</span>\s*•\s*'
    r'(?:(?P<size>[\d.]+)\s*(?P<unit>GB|MB)(?:\s*-\s*[\d.]+\s*GB)?|(?P<usage>[A-Za-z ]+?Usage))\s*•\s*'
    r'(?P<ctx>[\dKM]+)\s+context window\s*•\s*<span[^>]*>\s*(?P<input>[^•<]*?)\s+input',
    re.S)
MAKERS = [("qwen", "Alibaba"), ("glm", "Z.ai"), ("kimi", "Moonshot"), ("deepseek", "DeepSeek"),
          ("minimax", "MiniMax"), ("nemotron", "NVIDIA"), ("ministral", "Mistral"), ("mistral", "Mistral"),
          ("devstral", "Mistral"), ("magistral", "Mistral"), ("gemma", "Google"), ("granite", "IBM"),
          ("llama", "Meta"), ("olmo", "Ai2"), ("lfm", "Liquid AI"), ("phi", "Microsoft"),
          ("gpt-oss", "OpenAI"), ("cogito", "Deep Cogito"), ("ornith", "Ornith")]


def get(url):
    r = requests.get(url, timeout=30, headers=UA)
    r.raise_for_status()
    return r.text


def ram_for(gb, buckets):
    """Memory to run it with the OS and a long context alongside: weights × 1.2 + 3 GB."""
    need = gb * 1.2 + 3
    return next((b for b in buckets if b >= need), buckets[-1])


def pulls(s):
    m = re.match(r"([\d.]+)\s*([KM]?)", s or "")
    if not m:
        return 0
    return float(m.group(1)) * {"K": 1e3, "M": 1e6}.get(m.group(2), 1)


def maker_of(fam):
    return next((mk for p, mk in MAKERS if fam.startswith(p)), "")


def library(html):
    """One entry per family on a library page: capabilities, pulls, updated, description."""
    out = {}
    for block in re.split(r"<li\b", html)[1:]:
        m = re.search(r'href="/library/([a-z0-9.\-_]+)"', block)
        if not m:
            continue
        toks = [t.strip() for t in re.findall(r">([^<>]+)<", block) if t.strip()]
        caps = {t for t in toks if t in ("vision", "tools", "thinking", "cloud", "embedding", "audio", "decision")}
        p = toks[toks.index("Pulls") - 1] if "Pulls" in toks and toks.index("Pulls") > 0 else ""
        up = toks[toks.index("Updated") + 1] if "Updated" in toks and toks.index("Updated") + 1 < len(toks) else ""
        desc = next((t for t in toks if len(t) > 40), "")
        out[m.group(1)] = {"caps": caps, "pulls": pulls(p), "updated": up, "desc": desc}
    return out


def parse(html, family):
    """Plain local tags and cloud tags of one family."""
    rows, seen = [], set()
    for m in ROW.finditer(html):
        tag = m.group("tag")
        if not tag.startswith(family + ":") or tag in seen:
            continue
        cloud = tag.endswith(":cloud") or tag.endswith("-cloud")
        if cloud and re.search(r":\d{4}-cloud$", tag):      # date-pinned copies
            continue
        if not cloud and (SKIP_LOCAL.search(tag.lower()) or "cloud" in tag):
            continue
        seen.add(tag)
        row = {"tag": tag, "where": "cloud" if cloud else "local", "context": m.group("ctx"),
               "vision": "Image" in m.group("input")}
        if cloud:
            row["usage"] = (m.group("usage") or "").strip()
        elif m.group("size"):
            row["gb"] = round(float(m.group("size")) / (1000 if m.group("unit") == "MB" else 1), 1)
        else:
            continue
        rows.append(row)
    return rows


WORDS = {"glm": "GLM", "kimi": "Kimi", "deepseek": "DeepSeek", "minimax": "MiniMax", "gpt": "gpt",
         "nemotron": "Nemotron", "mistral": "Mistral", "ministral": "Ministral", "granite": "Granite",
         "devstral": "Devstral", "olmo": "OLMo", "lfm": "LFM", "phi": "Phi", "llama": "Llama"}


def name_of(tag):
    """qwen3.5:9b → Qwen3.5 9B · glm-5.3-flash:cloud → GLM-5.3 Flash (cloud)"""
    fam, size = tag.split(":", 1)
    cloud = size.endswith("cloud")
    size = re.sub(r"-?cloud$", "", size)
    if fam.startswith("qwen"):
        head = "Qwen" + fam[4:]
    elif fam.startswith("gemma"):
        head = "Gemma " + fam[5:]
    else:
        parts = fam.split("-")
        words = [WORDS.get(p, p[:1].upper() + p[1:]) for p in parts]
        # the maker and its version stay joined: GLM-5.3, Kimi-K3, gpt-oss
        head = "-".join(words[:2]) + ("".join(" " + w for w in words[2:]))
        head = head.replace("Gpt-Oss", "gpt-oss").replace("gpt-Oss", "gpt-oss").replace("Deepseek-R1", "DeepSeek-R1")
    out = f"{head} {size.upper()}".strip() if size else head
    return out + (" (cloud)" if cloud else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous")
    ap.add_argument("--changes")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, "local.json")))
    disc = cfg.get("discover", {})
    today = datetime.date.today().isoformat()

    prev_models, prev_found = {}, {}
    if a.previous and os.path.exists(a.previous):
        p = json.load(open(a.previous))
        for m in p.get("models", []):
            prev_models.setdefault(m["family"], []).append(m)
        for f in p.get("found", []):
            prev_found[f["family"]] = f

    # 1 · families: kept by hand, found before, found now
    families = {f["family"]: dict(f, found=None) for f in cfg["families"]}
    for fam, f in prev_found.items():
        families.setdefault(fam, {"family": fam, "maker": f.get("maker", ""), "tools": True, "thinking": True,
                                  "good": f.get("good", {}), "found": f.get("found")})
    new_now = []
    try:
        lib = {}
        for sort in ("popular", "newest"):
            lib.update(library(get(f"https://ollama.com/library?sort={sort}")))
        for fam, e in lib.items():
            if fam in families or fam in disc.get("skip", []):
                continue
            if not (e["caps"] & {"tools", "thinking"}) or e["caps"] & {"embedding", "decision"}:
                continue
            # used enough — or just out (this month), when nobody has pulled it yet
            fresh = re.search(r"hour|day|week|^1 month", e["updated"]) is not None
            if "year" in e["updated"] or e["pulls"] < (disc.get("minPullsNew", 5000) if fresh else disc.get("minPulls", 100000)):
                continue
            good = {"en": e["desc"], "zh": e["desc"]}
            families[fam] = {"family": fam, "maker": maker_of(fam), "tools": "tools" in e["caps"],
                             "thinking": "thinking" in e["caps"], "good": good, "found": today}
            new_now.append(fam)
    except Exception as e:
        print(f"⚠ library pages: {e} — no new families this week", file=sys.stderr)

    # 2 · tags
    models, loaded, failed = [], 0, []
    for fam, f in families.items():
        try:
            rows = parse(get(f"https://ollama.com/library/{fam}/tags"), fam)
            if not rows:
                raise ValueError("no tags parsed")
            loaded += 1
            for x in rows:
                m = {**x, "family": fam, "maker": f.get("maker", ""), "name": name_of(x["tag"]),
                     "tools": f.get("tools", True), "thinking": f.get("thinking", True),
                     "good": f.get("good", {}), "read": today}
                if x["where"] == "local":
                    m["ramGB"] = ram_for(x["gb"], cfg["ramBuckets"])
                if f.get("found"):
                    m["found"] = f["found"]
                models.append(m)
        except Exception as e:
            failed.append(fam)
            print(f"⚠ {fam}: {e} — keeping last week's rows", file=sys.stderr)
            for x in prev_models.get(fam, []):
                models.append({**x, "stale": True})
    if loaded == 0:
        print("⛔ nothing loaded; not writing", file=sys.stderr)
        sys.exit(1)

    # 3 · picks: local tags in `prefer` only
    have = {m["tag"]: m for m in models if m.get("where", "local") == "local"}
    picks = []
    for b in cfg["ramBuckets"]:
        t = next((p for p in cfg["prefer"] if p in have and have[p]["ramGB"] <= b), None)
        if t:
            picks.append({"ramGB": b, "tag": t})

    found = [{"family": fam, "maker": f.get("maker", ""), "good": f.get("good", {}), "found": f["found"]}
             for fam, f in families.items() if f.get("found")]
    out = {"version": 1, "date": today, "source": cfg["source"],
           "note": "where = local (runs on the Mac; gb is Ollama's download size, ramGB the Mac memory MAT asks for: weights × 1.2 + 3 GB) or cloud (runs in Ollama's cloud: needs `ollama signin`, has usage limits, the prompt leaves the Mac). Picks are local only and follow a hand-kept preference order, not a benchmark. Families under `found` were picked up from ollama.com automatically and are listed, not recommended.",
           "picks": picks, "found": found,
           "models": sorted(models, key=lambda m: (m["family"], m.get("where", "local"), m.get("gb", 0)))}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)

    if a.changes:
        lines = [f"# 本机 / Ollama 模型表 · {today}", "",
                 f"- {len(models)} 个 tag（本地 {sum(1 for m in models if m.get('where','local')=='local')}，云端 {sum(1 for m in models if m.get('where')=='cloud')}），{loaded}/{len(families)} 个家族读到。",
                 "- 推荐：" + "，".join(f"{p['ramGB']} GB → {p['tag']}" for p in picks)]
        if new_now:
            lines += ["", "## 本周新发现的家族（只进表，不进推荐；要推荐就加进 local.json 的 prefer）", ""]
            lines += [f"- **{fam}**（{families[fam].get('maker') or '未知厂商'}）：{families[fam]['good'].get('en','')}" for fam in new_now]
        if failed:
            lines += ["", "## 没读到（沿用上周）", ""] + [f"- {fam}" for fam in failed]
        os.makedirs(os.path.dirname(os.path.abspath(a.changes)), exist_ok=True)
        open(a.changes, "w").write("\n".join(lines) + "\n")
    print(f"✅ {len(models)} tags from {loaded}/{len(families)} families; new: {', '.join(new_now) or 'none'}")


if __name__ == "__main__":
    main()
