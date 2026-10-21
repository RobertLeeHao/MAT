#!/usr/bin/env python3
"""Step 2 of the weekly rebuild: turn the matched sources into MAT's rankings.

  python build.py --sources ../data/2026-10-19/sources.json --out ../v2/2026-10-19.json

For every kind of work x quality bar: which model, at which effort, with or
without a second model checking, clears the bar at the lowest expected cost
per finished job inside the bar's time limit. Every assumption is a named
constant below; the method is written up in rankings/README.md.
"""
import argparse, json, math, os, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# ───────────────────────── assumptions ─────────────────────────
TIERS = [
    dict(id="draft",    zh="草稿", en="Draft",    bar=0.60, cap=45,  b=22, review=False),
    dict(id="usable",   zh="可用", en="Usable",   bar=0.80, cap=90,  b=34, review=False),
    dict(id="deliver",  zh="交付", en="Deliver",  bar=0.92, cap=240, b=44, review=False),
    dict(id="critical", zh="关键", en="Critical", bar=0.97, cap=600, b=48, review=True),
]
SLOPE = 4.0           # Intelligence Index points per logit: p = sigmoid((score - b) / SLOPE)
REVIEW_EASE = 3.0     # judging an answer is ~3 points easier than producing it
MAX_RETRIES = 2       # a rejected answer is redone at most twice
W_GENERAL = 0.4       # weight of the general Intelligence Index in every text domain
PROFILE = {"agents": (20000, 4000), "search": (40000, 3000), "reasoning": (15000, 4000),
           "writing": (12000, 3000), "factuality": (25000, 1500), "coding": (20000, 6000),
           "instructionFollowing": (8000, 1500), "vision": (12000, 1500)}
THINK_MULT = {"agents": 1.5, "search": 1.0, "reasoning": 2.0, "writing": 0.6, "factuality": 1.0,
              "coding": 2.0, "instructionFollowing": 0.6, "vision": 0.8}
EFFORT_SENS = {"agents": 1.0, "search": 0.8, "reasoning": 1.0, "writing": 0.3, "factuality": 0.6,
               "coding": 1.0, "instructionFollowing": 0.5, "vision": 0.6}
OVERHEAD_S = {"search": 12.0}
DEFAULT_OVERHEAD_S = 1.0
REVIEW_OUT = 600
CATEGORIES = ["agents", "search", "reasoning", "writing", "factuality", "coding", "instructionFollowing", "vision"]

# Which sources make up each kind of work, and how much each counts.
# aa_* come from the Artificial Analysis row for the model's anchor effort.
SOURCES = {
    "agents": [("aa_gdpval", .5), ("vals_index", .25), ("arena_agent", .25)],
    "coding": [("vals_terminal_bench_4", .3), ("arena_webdev", .25), ("arena_coding", .15),
               ("aa_terminal_bench_40", .1), ("vals_swebench", .1), ("vals_terminal_bench_2_1", .1)],
    "search": [("arena_search", .6), ("arena_overall", .4)],
    "reasoning": [("arena_math", .4), ("vals_proofbench", .3), ("aa_hle", .2), ("scale_hle_diamond", .1)],
    "writing": [("arena_creative_writing", .5), ("arena_chinese", .3), ("eqbench_creative_writing", .2)],
    "factuality": [("aa_omniscience", 1.0)],
    "instructionFollowing": [("arena_instruction_following", .8), ("aa_ifbench", .2)],
    "vision": [("arena_vision", .5), ("arena_document", .2), ("vals_mmmu", .15), ("aa_mmmu", .15)],
}
AA_BENCH = {"aa_gdpval": "gdpval", "aa_omniscience": "omniscience", "aa_hle": "hle", "aa_ifbench": "ifbench",
            "aa_mmmu": "mmmuPro", "aa_terminal_bench_40": "terminalBench40"}
LABEL = {"aa_gdpval": "GDPval-AA", "vals_index": "Vals Index", "arena_agent": "Arena Agent",
         "vals_terminal_bench_4": "Terminal-Bench 4.0 (Vals)", "arena_webdev": "Arena WebDev", "arena_coding": "Arena Coding",
         "aa_terminal_bench_40": "Terminal-Bench 4.0 (AA)", "vals_swebench": "SWE-bench Verified", "vals_terminal_bench_2_1": "Terminal-Bench 2.1",
         "arena_search": "Arena Search", "arena_overall": "Arena Text", "arena_math": "Arena Math", "vals_proofbench": "ProofBench",
         "aa_hle": "Humanity's Last Exam (AA)", "scale_hle_diamond": "HLE-Diamond (Scale)",
         "arena_creative_writing": "Arena Creative Writing", "arena_chinese": "Arena Chinese",
         "eqbench_creative_writing": "EQ-Bench Creative Writing", "aa_omniscience": "AA-Omniscience",
         "arena_instruction_following": "Arena Instruction Following", "aa_ifbench": "IFBench",
         "arena_vision": "Arena Vision", "arena_document": "Arena Document", "vals_mmmu": "MMMU-Pro (Vals)", "aa_mmmu": "MMMU-Pro (AA)",
         "arena_text_to_image": "Arena Text-to-Image", "arena_image_edit": "Arena Image Edit"}
# 2026-10-21 · a source that measures general ability, not this kind of work.
# It still counts toward the score, but not as evidence for the domain.
PROXY = {"arena_overall"}
# How far to lean against a model the domain's own sources have not measured:
# the score used is a lower confidence bound, score − K × (share of the
# domain's own sources missing) × σ, where σ is how far, across the models
# that WERE measured, the domain score strays from the general Index. A
# model known only by its general Index is assumed one σ worse than that
# Index alone suggests (Hugo 10-21: Gemini 4 Argon topped Search with no
# search score at all).
UNCERT_K = 1.0
IMG_SRC = [("arena_text_to_image", .6), ("arena_image_edit", .4)]
IMG_B = {"draft": -1.5, "usable": -0.5, "deliver": 0.4, "critical": 1.0}
IMG_SLOPE = 0.5


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def build(reg, src, include_local=False):
    models = {m["id"]: dict(m) for m in reg["models"]}
    fails_plan = set(reg.get("failsPlanChecks", []))
    notes = []

    # ── prices: AA list price, else OpenRouter, else the registry's override
    price_src = {}
    for mid, m in models.items():
        if m.get("image") or m.get("local"):
            continue
        aa_rows = src["aa"].get(mid, [])
        pr = next((r for r in aa_rows if r.get("pin") is not None and r.get("pout") is not None), None)
        orr = src.get("openrouter", {}).get(mid)
        if pr:
            m["pin"], m["pout"], price_src[mid] = pr["pin"], pr["pout"], "artificialanalysis.ai"
            if pr.get("pcache") is not None:
                m["pcache"] = pr["pcache"]
            if orr and orr["pout"] and abs(orr["pout"] - pr["pout"]) / pr["pout"] > 0.25:
                notes.append(f"{m['name']}: OpenRouter's cheapest route charges ${orr['pin']:.2f}/${orr['pout']:.2f}, list price ${pr['pin']:g}/${pr['pout']:g}")
        elif m.get("priceOverride"):
            o = m["priceOverride"]
            m["pin"], m["pout"], price_src[mid] = o["pin"], o["pout"], o.get("src", "registry")
        elif orr:
            m["pin"], m["pout"], price_src[mid] = orr["pin"], orr["pout"], "openrouter.ai"

    # ── effort variants
    variants = defaultdict(list)
    for mid, rows in src["aa"].items():
        if mid not in models:
            continue
        for r in rows:
            variants[mid].append(dict(effort=r["effort"], ii=r.get("ii"), tps=r.get("tps"), ttft=r.get("ttft"),
                                      e2e=r.get("e2e"), cpt=r.get("costPerTask"), est=bool(r.get("iiEstimated")), row=r))

    def think_from_e2e(v):
        if v["e2e"] is None or not v["tps"]:
            return None
        return max(0.0, (v["e2e"] - 0.8) * v["tps"] - 500)

    ratios = []
    for mid, vs in variants.items():
        pout = models[mid].get("pout") or 0
        for v in vs:
            t = think_from_e2e(v)
            if t and v["cpt"] and pout:
                ratios.append(t / (v["cpt"] / pout * 1e6))
    k_think = st.median(ratios) if ratios else 0.05

    all_tps = [v["tps"] for vs in variants.values() for v in vs if v["tps"]]
    for mid, vs in variants.items():
        pout = models[mid].get("pout") or 0
        fam = [v["tps"] for v in vs if v["tps"]]
        for v in vs:
            v["think"], v["thinkEst"] = think_from_e2e(v), False
            if v["think"] is None:
                sib = [s for s in vs if s is not v and think_from_e2e(s) is not None and s["cpt"]]
                if sib and v["cpt"]:
                    s = min(sib, key=lambda s: abs((s["ii"] or 0) - (v["ii"] or 0)))
                    v["think"] = think_from_e2e(s) * v["cpt"] / s["cpt"]
                elif v["cpt"] and pout:
                    v["think"] = k_think * v["cpt"] / pout * 1e6
                else:
                    v["think"] = 1500.0
                v["thinkEst"] = True
            if not v["tps"]:
                v["tps"], v["tpsEst"] = (st.median(fam) if fam else st.median(all_tps)), True
                if not fam:
                    notes.append(f"{models[mid]['name']}: no speed measured yet; using the median of all models")
    for mid, m in models.items():
        if m.get("local"):
            for v in variants.get(mid, []):
                v["tps"] = m.get("localTps") or v["tps"]
        if not m.get("image") and mid not in variants:
            variants[mid] = [dict(effort="default", ii=None, tps=m.get("localTps") or (st.median(all_tps) if all_tps else 60),
                                  ttft=None, e2e=None, cpt=None, est=True, think=1500.0, thinkEst=True, tpsEst=True, row={})]
    for mid in variants:
        variants[mid] = [v for v in variants[mid] if v["effort"] != "max"] or variants[mid]

    def anchor(mid):
        vs = variants.get(mid, [])
        for e in ["high", "default", "xhigh", "medium"]:
            for v in vs:
                if v["effort"] == e and v["ii"] is not None:
                    return v
        vs2 = [v for v in vs if v["ii"] is not None]
        return max(vs2, key=lambda v: v["ii"]) if vs2 else None

    general = {mid: anchor(mid)["ii"] for mid in models if anchor(mid)}

    # ── benchmark tables, AA ones read at the anchor effort
    scores = {k: dict(v) for k, v in src["bench"].items()}
    for key, field in AA_BENCH.items():
        scores[key] = {}
        for mid in models:
            a = anchor(mid)
            if a and a["row"].get(field) is not None:
                scores[key][mid] = a["row"][field]

    def equate(key):
        xs = scores.get(key, {})
        both = [m for m in xs if m in general]
        if len(both) < 4:
            return {}
        mx, sx = st.mean(xs[m] for m in both), st.pstdev(xs[m] for m in both)
        mg, sg = st.mean(general[m] for m in both), st.pstdev(general[m] for m in both)
        return {} if sx == 0 else {m: mg + sg * (v - mx) / sx for m, v in xs.items()}

    theta, coverage, signals = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    spread = {}
    for cat, srcs in SOURCES.items():
        eq = {s: equate(s) for s, _ in srcs}
        own_w = sum(w for s, w in srcs if s not in PROXY) or 1.0
        # how far this domain's own scores stray from the general Index
        resid = []
        for mid in general:
            got = [(w, eq[s][mid]) for s, w in srcs if s not in PROXY and mid in eq[s]]
            if got:
                resid.append(sum(w * x for w, x in got) / sum(w for w, _ in got) - general[mid])
        sigma = st.pstdev(resid) if len(resid) >= 4 else 0.0
        spread[cat] = round(sigma, 2)
        for mid, m in models.items():
            if m.get("image"):
                continue
            num = den = own = 0.0
            sig = []
            for s, w in srcs:
                if mid in eq[s]:
                    num += w * eq[s][mid]; den += w
                    if s not in PROXY:
                        own += w
                    v = scores[s][mid]
                    sig.append(f"{LABEL.get(s, s)} {v:.3g}" if isinstance(v, float) and abs(v) < 10 else f"{LABEL.get(s, s)} {v:.0f}")
            if mid in general:
                num += W_GENERAL * general[mid]; den += W_GENERAL
            if den == 0:
                continue
            cov = own / own_w
            theta[cat][mid] = num / den - UNCERT_K * (1 - cov) * sigma
            coverage[cat][mid], signals[cat][mid] = round(cov, 2), sig

    def can_do(cat, mid):
        m = models[mid]
        return not m.get("image") and not (cat == "vision" and not m.get("reads"))

    def p_pass(th, b):
        return sigmoid((th - b) / SLOPE)

    def seat(cat, mid, v, reviewing=False):
        m = models[mid]
        pin, pout = (0.0, 0.0) if m.get("local") else (m.get("pin") or 0.0, m.get("pout") or 0.0)
        tin, tout = PROFILE[cat]
        think = v["think"] * THINK_MULT[cat]
        if reviewing:
            tin, tout, think = tin + tout, REVIEW_OUT, think * 0.7
        return (tin * pin + (tout + think) * pout) / 1e6, OVERHEAD_S.get(cat, DEFAULT_OVERHEAD_S) + (tout + think) / (v["tps"] or 50)

    def vtheta(cat, mid, v):
        a = anchor(mid)
        base = theta[cat][mid]
        return base if (a is None or v["ii"] is None) else base + EFFORT_SENS[cat] * (v["ii"] - a["ii"])

    boards = []
    for cat in CATEGORIES:
        cands = []
        for mid in theta[cat]:
            if not can_do(cat, mid) or (cat == "agents" and mid in fails_plan):
                continue
            if models[mid].get("local") and not include_local:
                continue   # free only on a Mac that has it: the app adds these back per person
            for v in variants[mid]:
                c, t = seat(cat, mid, v)
                cands.append(dict(m=mid, effort=v["effort"], th=vtheta(cat, mid, v), c=c, t=t, v=v))
        rows = []
        for mid in sorted(theta[cat], key=lambda x: -theta[cat][x]):
            if not can_do(cat, mid):
                continue
            vs = []
            for v in variants[mid]:
                th = vtheta(cat, mid, v); c, t = seat(cat, mid, v)
                vs.append(dict(effort=v["effort"], score=round(th, 1), p={T["id"]: round(p_pass(th, T["b"]), 3) for T in TIERS},
                               c=round(c, 5), t=round(t, 1), est=bool(v.get("thinkEst") or v.get("tpsEst"))))
            rows.append(dict(m=mid, score=round(theta[cat][mid], 1), coverage=coverage[cat][mid], sig=signals[cat][mid],
                             est=coverage[cat][mid] < 0.3, why=("failsPlanChecks" if cat == "agents" and mid in fails_plan else None),
                             variants=vs))
        picks = {}
        for T in TIERS:
            opts = []
            for x in cands:
                p = p_pass(x["th"], T["b"])
                if not T["review"]:
                    opts.append(dict(exec=x, rev=None, P=p, cost=x["c"], time=x["t"]))
                for r in cands:
                    if r["m"] == x["m"]:
                        continue
                    pr = p_pass(r["th"], T["b"] - REVIEW_EASE)
                    rc, rt = seat(cat, r["m"], r["v"], reviewing=True)
                    q = (1 - p) * pr
                    rounds = sum(q ** i for i in range(MAX_RETRIES + 1))
                    opts.append(dict(exec=x, rev=r, P=p * rounds, cost=(x["c"] + rc) * rounds, time=(x["t"] + rt) * rounds))
            ok = sorted([o for o in opts if o["P"] >= T["bar"] and o["time"] <= T["cap"]], key=lambda o: (round(o["cost"], 6), o["time"]))

            def fmt(o):
                d = dict(m=o["exec"]["m"], effort=o["exec"]["effort"], P=round(o["P"], 3), cost=round(o["cost"], 5), time=round(o["time"], 1))
                if o["rev"]:
                    d["reviewer"], d["reviewerEffort"] = o["rev"]["m"], o["rev"]["effort"]
                return d
            seen, top = set(), []
            for o in ok:
                if o["exec"]["m"] not in seen:
                    seen.add(o["exec"]["m"]); top.append(fmt(o))
            front, best_t = [], float("inf")
            for o in ok:
                if o["time"] < best_t - 1e-9:
                    front.append(fmt(o)); best_t = o["time"]
            best = None
            if not ok:
                inside = [o for o in opts if o["time"] <= T["cap"]]
                if inside:
                    best = fmt(max(inside, key=lambda o: (round(o["P"], 3), -o["cost"])))
            picks[T["id"]] = dict(cheapest=top, frontier=front, fastest=front[-1] if front else None,
                                  feasible=len(ok), bestEffort=best)
        boards.append(dict(category=cat, rows=rows, picks=picks))

    # ── image generation
    img = [mid for mid, m in models.items() if m.get("image")]
    z = {}
    for s, w in IMG_SRC:
        xs = {m: scores[s][m] for m in img if m in scores.get(s, {})}
        if len(xs) < 3:
            continue
        mu, sd = st.mean(xs.values()), st.pstdev(xs.values())
        for m, v in xs.items():
            z.setdefault(m, []).append((w, (v - mu) / sd))
    img_th = {m: sum(w * v for w, v in l) / sum(w for w, _ in l) for m, l in z.items()}
    img_rows, img_picks = [], {}
    for m in sorted(img_th, key=lambda x: -img_th[x]):
        img_rows.append(dict(m=m, score=round(img_th[m], 2),
                             sig=[f"{LABEL[s]} {scores[s][m]:.0f}" for s, _ in IMG_SRC if m in scores.get(s, {})],
                             p={t: round(sigmoid((img_th[m] - b) / IMG_SLOPE), 3) for t, b in IMG_B.items()},
                             c=models[m].get("perImage"), t=models[m].get("secondsPerImage")))
    for T in TIERS:
        opts = []
        for m in img_th:
            ppi, sec = models[m].get("perImage"), models[m].get("secondsPerImage") or 20
            if ppi is None:
                continue
            p = sigmoid((img_th[m] - IMG_B[T["id"]]) / IMG_SLOPE)
            for k in (1, 2, 3):
                opts.append(dict(m=m, k=k, P=round(1 - (1 - p) ** k, 3), cost=round(k * ppi + (0.003 if k > 1 else 0), 4),
                                 time=sec + (6 if k > 1 else 0)))
        ok = sorted([o for o in opts if o["P"] >= T["bar"] and o["time"] <= T["cap"]], key=lambda o: (o["cost"], o["time"]))
        seen, top = set(), []
        for o in ok:
            if o["m"] not in seen:
                seen.add(o["m"]); top.append(o)
        img_picks[T["id"]] = dict(cheapest=top, fastest=min(ok, key=lambda o: o["time"]) if ok else None, feasible=len(ok))
    boards.append(dict(category="imageGeneration", rows=img_rows, picks=img_picks))

    out_models = []
    for mid, m in sorted(models.items()):
        d = {k: m.get(k) for k in ["id", "name", "maker", "image", "local", "reads", "pin", "pcache", "pout",
                                    "perImage", "secondsPerImage", "match", "deprecated", "priceNote"] if m.get(k) is not None}
        if mid in variants and not m.get("image"):
            d["variants"] = [dict(effort=v["effort"], ii=v["ii"] and round(v["ii"], 1), tps=v["tps"] and round(v["tps"], 1),
                                  thinkTokens=round(v["think"]), e2e=v["e2e"] and round(v["e2e"], 1),
                                  est=bool(v.get("thinkEst") or v.get("tpsEst") or v.get("est")))
                             for v in variants[mid]]
        d["priceSource"] = price_src.get(mid)
        out_models.append(d)

    return dict(
        version=2, fetched=src["fetched"],
        sources={k: {kk: s.get(kk) for kk in ["ok", "url", "updated", "staleSince", "subset", "category", "matched"] if s.get(kk) is not None}
                 for k, s in src["status"].items()},
        attribution=["Arena leaderboard data (lmarena-ai/leaderboard-dataset), CC BY 4.0",
                     "Artificial Analysis (artificialanalysis.ai)", "Vals AI (vals.ai)", "Scale Labs (labs.scale.com)", "EQ-Bench (eqbench.com)"],
        tiers=[{k: T[k] for k in ["id", "zh", "en", "bar", "cap", "b", "review"]} for T in TIERS],
        method=dict(proxy=sorted(PROXY), uncertK=UNCERT_K, spread=spread, slope=SLOPE, maxRetries=MAX_RETRIES, reviewEase=REVIEW_EASE, wGeneral=W_GENERAL, profile=PROFILE,
                    thinkMult=THINK_MULT, effortSens=EFFORT_SENS, sources={k: v for k, v in SOURCES.items()},
                    kThink=round(k_think, 4), imageSources=IMG_SRC, imageB=IMG_B, imageSlope=IMG_SLOPE),
        notes=notes, models=out_models, boards=boards)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--include-local", action="store_true")
    a = ap.parse_args()
    reg = json.load(open(os.path.join(HERE, "registry.json")))
    res = build(reg, json.load(open(a.sources)), include_local=a.include_local)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), ensure_ascii=False, separators=(",", ":"))
    print("built", len(res["models"]), "models,", sum(len(b["rows"]) for b in res["boards"]), "rows")


if __name__ == "__main__":
    main()
