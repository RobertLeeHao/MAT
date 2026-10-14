#!/usr/bin/env python3
"""Can the weekly rankings pipeline read its sources without a person or an LLM?

For every source in sources.json it tries two ways in:
  raw     — a plain HTTP GET, the page as the server sends it
  render  — headless Chromium, the page after its scripts have run
and checks whether the numbers we already know (anchors: a model name and the
score that source gave it on 2026-10-14) can be found in what came back.

  raw hit     → a plain parser works (cheapest, sturdiest)
  render hit  → needs a browser step in the pipeline
  neither     → this source cannot be automated as is

Writes out/report.json, out/report.md (also the job summary), and the
fetched pages under out/pages/ so the real parsers can be written against them.
"""
import json, os, re, sys, time, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(os.path.join(OUT, "pages"), exist_ok=True)
UA = "Mozilla/5.0 (compatible; MAT-rankings-probe/0.1; +https://github.com/RobertLeeHao/MAT)"

import requests

def norm(s):
    return re.sub(r"[^a-z0-9.]", "", s.lower())

def name_keys(name):
    """'Claude Opus 5.5' → also 'claude-opus-5-5', 'opus 5.5' … compared after norm()."""
    n = name.lower()
    keys = {n, n.replace(" ", "-"), n.replace(".", "-").replace(" ", "-"), n.replace(" ", "")}
    parts = n.split(" ", 1)
    if len(parts) == 2 and parts[0] in ("claude", "gemini", "gpt"):
        keys.add(parts[1])
    return {norm(k) for k in keys}

def check(text, anchors):
    t = norm(text)
    found = []
    for name, value in anchors:
        has_name = any(k and k in t for k in name_keys(name))
        has_val = True if value is None else (norm(value) in t)
        found.append(dict(name=name, value=value, name_found=has_name, value_found=has_val))
    return found

def score(found):
    return sum(1 for f in found if f["name_found"] and f["value_found"])

def save(sid, how, body):
    fn = re.sub(r"[^A-Za-z0-9_.-]", "_", sid) + f".{how}.txt"
    with open(os.path.join(OUT, "pages", fn), "w", encoding="utf-8") as f:
        f.write(body)
    return fn

def main():
    sources = json.load(open(os.path.join(HERE, "sources.json")))
    only = sys.argv[1:]  # optional ids
    results = []
    browser = None
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as e:
        print("no browser:", e)

    aa_key = os.environ.get("AA_API_KEY")
    for s in sources:
        if only and s["id"] not in only:
            continue
        r = dict(id=s["id"], url=s["url"], kind=s["kind"])
        # raw
        try:
            resp = requests.get(s["url"], headers={"User-Agent": UA}, timeout=40)
            r["raw_status"], r["raw_bytes"] = resp.status_code, len(resp.content)
            body = resp.text
            r["raw_file"] = save(s["id"], "raw", body)
            r["raw_found"] = check(body, s["anchors"])
            r["raw_hits"] = score(r["raw_found"])
            r["raw_has_next_data"] = ("__NEXT_DATA__" in body) or ("self.__next_f" in body)
        except Exception as e:
            r["raw_error"] = repr(e)[:300]
            r["raw_hits"] = 0
        # rendered
        if browser and s["kind"] != "json":
            try:
                page = browser.new_page(user_agent=UA)
                page.goto(s["url"], wait_until="networkidle", timeout=60000)
                time.sleep(2)
                text = page.inner_text("body")
                r["render_bytes"] = len(text)
                r["render_file"] = save(s["id"], "render", text)
                r["render_found"] = check(text, s["anchors"])
                r["render_hits"] = score(r["render_found"])
                page.close()
            except Exception as e:
                r["render_error"] = repr(e)[:300]
                r["render_hits"] = 0
        n = len(s["anchors"])
        r["anchors"] = n
        r["verdict"] = ("raw" if r.get("raw_hits") == n else
                        "render" if r.get("render_hits") == n else
                        "partial" if max(r.get("raw_hits", 0), r.get("render_hits", 0)) > 0 else
                        "blocked" if r.get("raw_status") in (401, 403, 429, 503) else
                        "unreachable" if r.get("raw_error") and (r.get("render_error") or not browser) else "no")
        results.append(r)
        print(f'{r["verdict"]:8} raw {r.get("raw_status")} {r.get("raw_hits")}/{n}  render {r.get("render_hits")}/{n}  {s["id"]}')
        time.sleep(1.5)  # polite

    # Artificial Analysis data API, only if a key was given as a repo secret
    if aa_key and (not only or "aa_api" in only):
        r = dict(id="aa_api", url="https://artificialanalysis.ai/api/v2/data/llms/models", kind="api")
        try:
            resp = requests.get(r["url"], headers={"x-api-key": aa_key, "User-Agent": UA}, timeout=40)
            r["raw_status"], r["raw_bytes"] = resp.status_code, len(resp.content)
            r["raw_file"] = save("aa_api", "raw", resp.text)
            r["verdict"] = "raw" if resp.ok else "no"
        except Exception as e:
            r["raw_error"], r["verdict"] = repr(e)[:300], "no"
        results.append(r)

    json.dump(dict(ran=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), results=results),
              open(os.path.join(OUT, "report.json"), "w"), indent=1, ensure_ascii=False)
    tally = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    lines = ["# Rankings sources probe", "", "Verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())), "",
             "| source | verdict | raw | render |", "|---|---|---|---|"]
    for r in results:
        lines.append(f'| {r["id"]} | {r["verdict"]} | {r.get("raw_status","–")} · {r.get("raw_hits","–")}/{r.get("anchors","–")} '
                     f'| {r.get("render_hits","–")}/{r.get("anchors","–")} |')
    md = "\n".join(lines)
    open(os.path.join(OUT, "report.md"), "w").write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(md + "\n")
    if browser:
        browser.close()

if __name__ == "__main__":
    main()
