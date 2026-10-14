#!/usr/bin/env python3
"""Step 3 of the weekly rebuild: check the new table, and say what changed since last week.

  python diff.py --new ../v2/archive/2026-10-19.json --old ../v2/latest.json \
                 --sources ../data/2026-10-19/sources.json --old-sources ../data/2026-10-12/sources.json \
                 --out ../v2/changes/2026-10-19.md

Exit code 1 means a gate failed: the table is not published, and the reason is
at the top of the changes file.
"""
import argparse, datetime, json, sys

STALE_DAYS = 21
REQUIRED = ["aa", "arena_overall"]
MIN_ROWS = 15
CATS = {"agents": "智能体", "search": "搜索调研", "reasoning": "推理分析", "writing": "写作", "factuality": "事实复核",
        "coding": "编程", "instructionFollowing": "遵循指令", "vision": "看图/文档", "imageGeneration": "出图"}
TIERS = {"draft": "草稿", "usable": "可用", "deliver": "交付", "critical": "关键"}


def load(p):
    try:
        return json.load(open(p)) if p else None
    except (OSError, ValueError):
        return None


def gates(new, src):
    errs = []
    today = datetime.date.fromisoformat(new["fetched"])
    for k in REQUIRED:
        s = src["status"].get(k, {})
        if not s.get("ok"):
            since = s.get("staleSince")
            if not since or (today - datetime.date.fromisoformat(since)).days > STALE_DAYS:
                errs.append(f"必需数据源 {k} 读取失败，且没有 {STALE_DAYS} 天内的旧数据可用：{s.get('error', '')}")
    for b in new["boards"]:
        if b["category"] != "imageGeneration" and len(b["rows"]) < MIN_ROWS:
            errs.append(f"{CATS[b['category']]} 只有 {len(b['rows'])} 个模型（至少 {MIN_ROWS}）")
        for t in ["draft", "usable", "deliver"]:
            if not b["picks"][t]["cheapest"]:
                errs.append(f"{CATS[b['category']]} · {TIERS[t]} 没有任何组合过线")
    return errs


def names(d):
    return {m["id"]: m["name"] for m in d["models"]}


def pick_line(o, N):
    if not o:
        return "—"
    if "k" in o:
        s = N.get(o["m"], o["m"]) + (f" ×{o['k']}" if o["k"] > 1 else "")
    else:
        s = f"{N.get(o['m'], o['m'])} · {o['effort']}"
        if o.get("reviewer"):
            s += f" + {N.get(o['reviewer'], o['reviewer'])} 复核"
    return f"{s}（{o['P'] * 100:.0f}% · ${o['cost']:.3f} · {o['time']:.0f}s）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True)
    ap.add_argument("--old")
    ap.add_argument("--sources", required=True)
    ap.add_argument("--old-sources")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    new, old, src, osrc = load(a.new), load(a.old), load(a.sources), load(a.old_sources)
    N = names(new)
    errs = gates(new, src)
    L = [f"# 排行榜周更 · {new['fetched']}", ""]
    if errs:
        L += ["## ⛔ 没有发布", "", *[f"- {e}" for e in errs], ""]
    else:
        L += ["✅ 已发布为 `latest.json`。" + ("" if old else "（第一期，没有上周可比。）"), ""]

    # sources
    L += ["## 数据源", "", "| 数据源 | 状态 | 数据日期 | 对上的模型 |", "|---|---|---|---|"]
    for k, s in src["status"].items():
        st = "✅" if s.get("ok") else (f"⚠️ 沿用 {s['staleSince']} 的数据" if s.get("staleSince") else "❌ 失败")
        L.append(f"| {k} | {st} | {s.get('updated') or '—'} | {s.get('matched', '—')} |")
    L.append("")

    # picks
    if old:
        ON = names(old)
        ob = {b["category"]: b for b in old["boards"]}
        ch = []
        for b in new["boards"]:
            for t in TIERS:
                n = (b["picks"][t]["cheapest"] or [None])[0]
                o = (ob.get(b["category"], {}).get("picks", {}).get(t, {}).get("cheapest") or [None])[0]
                key = lambda x: x and (x["m"], x.get("effort"), x.get("reviewer"), x.get("k"))
                if key(n) != key(o):
                    ch.append(f"| {CATS[b['category']]} | {TIERS[t]} | {pick_line(o, ON)} | {pick_line(n, N)} |")
        L += ["## 推荐变了的档位", ""]
        L += (["| 领域 | 档位 | 上周 | 本周 |", "|---|---|---|---|", *ch] if ch else ["没有变化。"]) + [""]

        # prices
        om = {m["id"]: m for m in old["models"]}
        pc = []
        for m in new["models"]:
            p = om.get(m["id"])
            if p and m.get("pout") is not None and p.get("pout") is not None and (m["pin"], m["pout"]) != (p.get("pin"), p.get("pout")):
                flag = " ⚠️ 变化超过 3 倍，请核对" if p["pout"] and (m["pout"] / p["pout"] > 3 or m["pout"] / p["pout"] < 1 / 3) else ""
                pc.append(f"- {m['name']}：${p.get('pin')}/${p['pout']} → ${m['pin']}/${m['pout']}{flag}")
        added = [N[i] for i in N if i not in ON]
        removed = [ON[i] for i in ON if i not in N]
        L += ["## 价格和模型", ""] + (pc or ["价格没有变化。"])
        if added:
            L.append(f"- 新加入：{'、'.join(added)}")
        if removed:
            L.append(f"- 移除：{'、'.join(removed)}")
        L.append("")
    else:
        L += ["## 本期推荐", "", "| 领域 | 草稿 | 可用 | 交付 | 关键 |", "|---|---|---|---|---|"]
        for b in new["boards"]:
            cells = [pick_line((b["picks"][t]["cheapest"] or [b["picks"][t].get("bestEffort")])[0], N) for t in TIERS]
            L.append(f"| {CATS[b['category']]} | " + " | ".join(cells) + " |")
        L.append("")

    # names nobody claims yet
    prev_un = {k: set(v) for k, v in (osrc or {}).get("unclaimed", {}).items()}
    fresh = {k: [n for n in v if n not in prev_un.get(k, set())] for k, v in src.get("unclaimed", {}).items()}
    fresh = {k: v for k, v in fresh.items() if v}
    L += ["## 还没对上的名字", "",
          "数据源里排名靠前、但 `registry.json` 里没有的名字" + ("（只列本周新出现的）" if osrc else "") + "。是新模型或改名的话，在 registry 里补一行别名。", ""]
    if fresh:
        for k, v in fresh.items():
            L.append(f"- **{k}**：{', '.join(v[:12])}")
    else:
        L.append("没有新的。")
    L.append("")
    if new.get("notes"):
        L += ["## 备注", "", *[f"- {n}" for n in new["notes"]], ""]

    open(a.out, "w").write("\n".join(L))
    print("\n".join(L[:12]))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
