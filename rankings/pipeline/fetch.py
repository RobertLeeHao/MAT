#!/usr/bin/env python3
"""Step 1 of the weekly rebuild: read every source and match it to MAT's models.

  python fetch.py --out ../data/2026-10-19/sources.json [--previous ../data/2026-10-12/sources.json]

A source that fails this week keeps last week's numbers, marked stale with the
day they were really read. Names a source uses that match no model in
registry.json are listed, so new models and renames show up in the changes.
"""
import argparse, datetime, json, os, re, sys, traceback

import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
EFFORT_SUFFIX = re.compile(r"^(-(high|low|medium|xhigh|max|minimal|reasoning|non-reasoning))?$")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def load_registry():
    return json.load(open(os.path.join(HERE, "registry.json")))


def match_simple(rows, reg, kind, pick="max"):
    """rows: [{name, value}] → {model id: value}, plus the top names nobody claims."""
    index = {}
    for m in reg["models"]:
        for a in (m["aliases"].get(kind) or []):
            index[norm(a)] = m["id"]
    got, unclaimed = {}, []
    for r in sorted(rows, key=lambda r: -(r.get("value") or 0)):
        mid = index.get(norm(r["name"]))
        if mid is None:
            if len(unclaimed) < 25:
                unclaimed.append(r["name"])
            continue
        if mid not in got or (pick == "max" and r["value"] > got[mid]):
            got[mid] = r["value"]
    return got, unclaimed


def match_aa(rows, reg):
    bases = {}
    for m in reg["models"]:
        for a in m["aliases"].get("aa") or []:
            bases[a] = m["id"]
    out, unclaimed = {}, []
    for r in sorted(rows, key=lambda r: -(r.get("ii") or 0)):
        mid = None
        for base, m in bases.items():
            if r["slug"] == base or (r["slug"].startswith(base + "-") and EFFORT_SUFFIX.match(r["slug"][len(base):])):
                mid = m
                break
        if mid is None:
            if not r.get("deprecated") and len(unclaimed) < 25:
                unclaimed.append(f'{r["slug"]} ({r["name"]})')
            continue
        out.setdefault(mid, []).append(r)
    return out, unclaimed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous")
    a = ap.parse_args()
    reg = load_registry()
    prev = json.load(open(a.previous)) if a.previous and os.path.exists(a.previous) else None
    today = datetime.date.today().isoformat()
    res = dict(fetched=today, status={}, aa={}, bench={}, openrouter={}, unclaimed={})

    def ok(key, src, matched, unclaimed):
        res["status"][key] = dict(ok=True, url=src.get("url"), updated=src.get("updated"), rows=len(src.get("rows", [])), matched=len(matched))
        res["unclaimed"][key] = unclaimed

    def failed(key, err, section, sub=None):
        """Keep last week's numbers for this source, marked with the day they were read."""
        st = dict(ok=False, error=str(err)[:300])
        if prev and key in prev.get("status", {}):
            old = prev["status"][key]
            st["staleSince"] = old.get("staleSince") or prev["fetched"]
            if sub is None:
                res[section] = prev.get(section, {})
            elif sub in prev.get(section, {}):
                res[section][sub] = prev[section][sub]
        res["status"][key] = st
        print(f"!! {key}: {err}", file=sys.stderr)

    # Artificial Analysis: one page, every model and effort
    try:
        src = S.fetch_aa()
        res["aa"], un = match_aa(src["rows"], reg)
        ok("aa", src, res["aa"], un)
    except Exception as e:
        traceback.print_exc()
        failed("aa", e, "aa")

    # Vals, Scale, EQ-Bench
    jobs = [(k, (lambda u=u: S.fetch_vals(u)), "vals") for k, u in S.VALS.items()]
    jobs += [("scale_hle_diamond", S.fetch_scale_hle, "scale"), ("eqbench_creative_writing", S.fetch_eqbench, "eqbench")]
    for key, fn, kind in jobs:
        try:
            src = fn()
            got, un = match_simple(src["rows"], reg, kind)
            res["bench"][key] = got
            ok(key, src, got, un)
        except Exception as e:
            failed(key, e, "bench", key)

    # Arena: Hugging Face public dataset
    try:
        boards = S.fetch_arena()
    except Exception as e:
        boards = {k: dict(error=repr(e)) for k in S.ARENA}
    for key, src in boards.items():
        if "error" in src:
            failed(key, src["error"], "bench", key)
            continue
        got, un = match_simple(src["rows"], reg, "arena")
        if src.get("scale", 1) != 1:
            got = {k: v * src["scale"] for k, v in got.items()}
        res["bench"][key] = got
        ok(key, src, got, un)
        res["status"][key].update(subset=src["subset"], category=src["category"])

    # OpenRouter prices (a cross-check; AA carries list prices)
    try:
        src = S.fetch_openrouter()
        idx = {m["aliases"].get("openrouter"): m["id"] for m in reg["models"] if m["aliases"].get("openrouter")}
        res["openrouter"] = {idx[r["name"]]: dict(pin=r["pin"], pout=r["pout"]) for r in src["rows"] if r["name"] in idx}
        ok("openrouter", src, res["openrouter"], [])
    except Exception as e:
        failed("openrouter", e, "openrouter")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1, ensure_ascii=False)
    bad = [k for k, s in res["status"].items() if not s["ok"]]
    print(f"sources: {len(res['status']) - len(bad)} ok, {len(bad)} failed {bad}")


if __name__ == "__main__":
    main()
