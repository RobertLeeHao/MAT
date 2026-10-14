"""Fetch and parse every source behind MAT's model rankings.

Each source returns plain records keyed by the source's own model names.
Matching those names to MAT's models happens in fetch.py, from registry.json.
Nothing here guesses a number: a field a page does not carry stays None.
"""
import html, io, json, re
import requests

UA = {"User-Agent": "MAT-rankings/2.0 (+https://github.com/RobertLeeHao/MAT)"}
TIMEOUT = 60


def get(url, timeout=TIMEOUT, **kw):
    r = requests.get(url, headers=UA, timeout=timeout, **kw)
    r.raise_for_status()
    return r


# ───────────────────────── page formats ─────────────────────────

def rsc_text(page):
    """Next.js pages carry their data as flight chunks: self.__next_f.push([1,"..."])."""
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[\d+,("(?:[^"\\]|\\.)*")\]\)', page):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return "".join(out)


def objects_with(text, key):
    """Every JSON object in `text` that has `key`, found by matching braces around each hit."""
    seen = set()
    for m in re.finditer(r'"%s":' % re.escape(key), text):
        i, depth = m.start(), 0
        while i > 0:
            c = text[i]
            if c == "}":
                depth += 1
            elif c == "{":
                if depth == 0:
                    break
                depth -= 1
            i -= 1
        j, depth, instr, esc = i, 0, False, False
        while j < len(text):
            c = text[j]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            elif c == '"':
                instr = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if (i, j) in seen:
            continue
        seen.add((i, j))
        try:
            yield json.loads(text[i:j + 1])
        except ValueError:
            pass


def _astro(v):
    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int):
        t, x = v
        if t == 0:
            return {k: _astro(y) for k, y in x.items()} if isinstance(x, dict) else x
        if t == 1:
            return [_astro(y) for y in x]
        return x
    if isinstance(v, dict):
        return {k: _astro(y) for k, y in v.items()}
    return v


def astro_islands(page):
    """Astro pages carry each component's data in its props attribute."""
    for m in re.finditer(r'<astro-island[^>]*?props="([^"]*)"', page):
        try:
            raw = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        yield {k: _astro(v) for k, v in raw.items()}


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ───────────────────────── Artificial Analysis ─────────────────────────

AA_FIELDS = {
    "ii": "intelligenceIndex", "iiEstimated": "intelligenceIndexIsEstimated",
    "pin": "price1mInputTokens", "pout": "price1mOutputTokens", "pcache": "cacheHitPrice",
    "tps": "medianOutputTokensPerSecond", "ttft": "medianTimeToFirstTokenSeconds",
    "ttfat": "medianTimeToFirstAnswerTokenSeconds", "e2e": "medianEndToEndResponseTimeSeconds",
    "costPerTask": "intelligenceIndexCostPerTask",
    "gdpval": "gdpvalNormalized", "omniscience": "omniscience", "omniscienceAccuracy": "omniscienceAccuracy",
    "hle": "hle", "ifbench": "ifbench", "mmmuPro": "mmmuPro", "lcr": "lcr",
    "terminalBench40": "terminalBench40", "terminalBench21": "terminalBench21", "tauBanking": "tauBanking",
}
EFFORTS = ["non-reasoning", "reasoning", "xhigh", "max", "high", "medium", "low", "minimal"]


def aa_effort(name):
    """'Claude Opus 5.5 (High, Default Fallback)' → 'high'; no brackets → 'default'."""
    m = re.search(r"\(([^)]*)\)\s*$", name or "")
    if not m:
        return "default"
    first = m.group(1).split(",")[0].strip().lower()
    if first == "non-reasoning":
        return "none"
    if first == "reasoning":
        return "default"
    return first if first in EFFORTS else "default"


def fetch_aa():
    page = get("https://artificialanalysis.ai/leaderboards/models").text
    text = rsc_text(page)
    rows = {}
    for o in objects_with(text, "intelligenceIndex"):
        if "slug" not in o or "medianOutputTokensPerSecond" not in o:
            continue
        r = {k: (o.get(v) if k == "iiEstimated" else num(o.get(v))) for k, v in AA_FIELDS.items()}
        r.update(slug=o["slug"], name=o.get("name"), effort=aa_effort(o.get("name")),
                 deprecated=bool(o.get("deprecated")), maker=o.get("modelCreatorName"))
        rows[o["slug"]] = r
    if len(rows) < 100:
        raise ValueError(f"only {len(rows)} models parsed from the AA leaderboard")
    return dict(url="https://artificialanalysis.ai/leaderboards/models", rows=list(rows.values()))


# ───────────────────────── Vals ─────────────────────────

VALS = {
    "vals_terminal_bench_4": "https://www.vals.ai/benchmarks/terminal-bench-4",
    "vals_terminal_bench_2_1": "https://www.vals.ai/benchmarks/terminal-bench-2-1",
    "vals_swebench": "https://www.vals.ai/benchmarks/swebench",
    "vals_index": "https://www.vals.ai/benchmarks/vals_index",
    "vals_proofbench": "https://www.vals.ai/benchmarks/proof_bench",
    "vals_mmmu": "https://www.vals.ai/benchmarks/mmmu",
}


def fetch_vals(url):
    page = get(url).text
    for props in astro_islands(page):
        bv = props.get("benchmarkView")
        if isinstance(bv, dict) and "tasks" in bv:
            overall = bv["tasks"].get("overall") or {}
            rows = [dict(name=k, value=num(v.get("accuracy"))) for k, v in overall.items() if num(v.get("accuracy")) is not None]
            if len(rows) < 10:
                raise ValueError(f"only {len(rows)} rows")
            return dict(url=url, updated=(bv.get("metadata") or {}).get("updated"), rows=rows)
    raise ValueError("no benchmarkView on the page")


# ───────────────────────── Scale ─────────────────────────

def fetch_scale_hle():
    url = "https://labs.scale.com/leaderboard/hle-diamond"
    text = rsc_text(get(url).text)
    for o in objects_with(text, "entries"):
        e = o.get("entries")
        if isinstance(e, list) and e and isinstance(e[0], dict) and "score" in e[0]:
            return dict(url=url, rows=[dict(name=x["model"], value=num(x.get("score"))) for x in e if num(x.get("score")) is not None])
    raise ValueError("no entries on the page")


# ───────────────────────── EQ-Bench ─────────────────────────

def fetch_eqbench():
    url = "https://eqbench.com/creative_writing.js"
    js = get(url).text
    m = re.search(r"leaderboardDataCreativeWritingV3\s*=\s*`([^`]*)`", js)
    if not m:
        raise ValueError("creative writing table not found")
    lines = [l for l in m.group(1).strip().splitlines() if l.strip()]
    head = lines[0].split(",")
    i_name, i_elo = head.index("model_name"), head.index("elo_score")
    rows = []
    for l in lines[1:]:
        c = l.split(",")
        try:
            rows.append(dict(name=c[i_name].lstrip("*"), value=float(c[i_elo])))
        except (ValueError, IndexError):
            pass
    return dict(url=url, rows=rows)


# ───────────────────────── OpenRouter ─────────────────────────

def fetch_openrouter():
    url = "https://openrouter.ai/api/v1/models"
    rows = []
    for m in get(url).json()["data"]:
        p = m.get("pricing") or {}
        try:
            rows.append(dict(name=m["id"], pin=float(p.get("prompt")) * 1e6, pout=float(p.get("completion")) * 1e6))
        except (TypeError, ValueError):
            pass
    return dict(url=url, rows=rows)


# ───────────────────────── Arena (public dataset, CC BY 4.0) ─────────────────────────

ARENA_DS = "lmarena-ai/leaderboard-dataset"
ARENA = {  # our key: (subset, category)
    "arena_overall": ("text_style_control", "overall"),
    "arena_coding": ("text_style_control", "coding"),
    "arena_math": ("text_style_control", "math"),
    "arena_creative_writing": ("text_style_control", "creative_writing"),
    "arena_chinese": ("text_style_control", "chinese"),
    "arena_instruction_following": ("text_style_control", "instruction_following"),
    "arena_vision": ("vision_style_control", "overall"),
    "arena_document": ("document_style_control", "overall"),
    "arena_search": ("search_style_control", "overall"),
    "arena_search_raw": ("search", "overall"),
    "arena_webdev": ("webdev", "overall"),
    "arena_text_to_image": ("text_to_image", "overall"),
    "arena_image_edit": ("image_edit", "overall"),
    "arena_agent": ("agent", "overall"),
}


def fetch_arena():
    import pandas as pd
    files = get(f"https://datasets-server.huggingface.co/parquet?dataset={ARENA_DS}").json()["parquet_files"]
    urls = {}
    for f in files:
        urls.setdefault((f["config"], f["split"]), []).append(f["url"])
    frames = {}
    out = {}
    for key, (subset, cat) in ARENA.items():
        try:
            if subset not in frames:
                parts = [pd.read_parquet(io.BytesIO(get(u, timeout=240).content)) for u in urls[(subset, "latest")]]
                frames[subset] = pd.concat(parts, ignore_index=True)
            df = frames[subset]
            d = df[df["category"] == cat].copy()
            if d.empty:
                raise ValueError(f"no rows for category {cat}")
            d["leaderboard_publish_date"] = d["leaderboard_publish_date"].astype(str).str[:10]
            # `latest` can hold an old board for a model no longer shown: keep each model's newest row
            d = d.sort_values("leaderboard_publish_date").drop_duplicates("model_name", keep="last")
            val = "rating" if "rating" in d.columns else "score"
            newest = d["leaderboard_publish_date"].max()
            vcol = next((c for c in ("vote_count", "observation_count") if c in d.columns), None)
            rows = []
            for _, r in d.iterrows():
                v = r[vcol] if vcol else None
                rows.append(dict(name=str(r["model_name"]), value=float(r[val]),
                                 votes=int(v) if v is not None and v == v else None, published=r["leaderboard_publish_date"]))
            out[key] = dict(url=f"https://huggingface.co/datasets/{ARENA_DS}", subset=subset, category=cat,
                            updated=newest, rows=rows, scale=(100.0 if val == "score" else 1.0))
        except Exception as e:  # one board failing must not lose the others
            out[key] = dict(error=repr(e)[:300])
    return out
