# MAT model rankings

Every Monday a GitHub Action rebuilds the table MAT staffs from. It reads public benchmarks, matches them to the models MAT can call, and publishes the result with the website:

- `https://robertleehao.github.io/MAT/rankings/v2/latest.json`: this week's table. The app and the website both read it.
- `…/rankings/v2/index.json`: every published week, with links to the archived table and its changes.
- `…/rankings/v2/changes/<date>.md`: what changed since the week before (in Chinese, for the maintainer).

## What the table answers

The table does not just rank models by strength. For each kind of work and each quality bar it answers one question: which model, at which effort, with or without a second model checking, clears the bar at the lowest expected cost per finished job inside the bar's time limit.

| Bar | Pass chance | Time per step |
|---|---|---|
| Draft | ≥ 60% | ≤ 45 s |
| Usable | ≥ 80% | ≤ 90 s |
| Deliver | ≥ 92% | ≤ 4 min |
| Critical | ≥ 97%, always checked by a second model | ≤ 10 min |

## Files

| Path | What it is |
|---|---|
| `pipeline/registry.json` | Every model MAT ranks, and the name each source uses for it. New models and renames are added here. |
| `pipeline/sources.py` | Reads each source and parses it. Nothing is guessed: a field a page does not carry stays empty. |
| `pipeline/fetch.py` | Matches source names to models. A source that fails keeps last week's numbers, marked stale. |
| `pipeline/build.py` | Turns scores, prices and speeds into pass chances, costs and picks. Every assumption is a named constant at the top. |
| `pipeline/diff.py` | Checks the new table and writes the changes. If a check fails, nothing is published. |
| `pipeline/run.sh` | Runs the steps above in order. |
| `data/<date>/sources.json` | What the sources said that week, after matching. |

## Sources

| Source | Used for | How it is read |
|---|---|---|
| [Arena](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) | Text, coding, math, creative writing, Chinese, instruction following, vision, documents, search, WebDev, agents, images | The public dataset on Hugging Face, `latest` split, style-controlled boards |
| [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models) | Intelligence Index for each effort level, list prices, speed, latency, GDPval-AA, AA-Omniscience, HLE, IFBench, MMMU-Pro, Terminal-Bench | The data embedded in the leaderboard page |
| [Vals AI](https://www.vals.ai) | Terminal-Bench 4.0 and 2.1, SWE-bench Verified, Vals Index, ProofBench, MMMU | The data embedded in each benchmark page |
| [Scale Labs](https://labs.scale.com/leaderboard/hle-diamond) | HLE-Diamond | The data embedded in the page |
| [EQ-Bench](https://eqbench.com/creative_writing.html) | Creative writing | The site's data file |
| [OpenRouter](https://openrouter.ai/api/v1/models) | A cross-check on prices | Public API |

Arena leaderboard data is © LMArena, licensed CC BY 4.0. Any page that shows these numbers credits Arena and links to the dataset.

## Checks before publishing

- Artificial Analysis and Arena's text board must have been read within the last 21 days. Last week's numbers count as read on the day they were fetched.
- Every kind of work must rank at least 15 models.
- Every kind of work must have a pick at the Draft, Usable and Deliver bars.

## Run it locally

```
pip install -r rankings/pipeline/requirements.txt
sh rankings/pipeline/run.sh
```

## Models MAT can reach through Ollama (`local/`)

`https://robertleehao.github.io/MAT/rankings/local/latest.json` lists every model MAT can call through Ollama — on the Mac (`where: local`) or in Ollama's cloud (`where: cloud`) — rebuilt every Monday in the same run (`pipeline/local_models.py`, a separate step: one failing never holds the other back). What changed is written to `local/changes/<date>.md`.

- `pipeline/local.json` (kept by hand): the families always read, what each is good for, and `prefer` — the order MAT recommends local models in. That order is a judgement, not a benchmark.
- New families are picked up by themselves: anything on ollama.com's popular or newest pages that holds a conversation (tools or thinking; not embedding or decision models), was updated within the last year and has ≥ 100K pulls — or ≥ 5K if it came out this month. `discover.skip` lists families that match but are not general chat models. Found families are listed under `found`, stay in the table on later weeks, and are never recommended until added to `prefer`.
- Local tags: download size, context window, whether it reads pictures, and `ramGB`, the Mac memory MAT asks for (weights × 1.2 + 3 GB). Cloud tags: Ollama's usage level instead of a size; they need `ollama signin`, count against Ollama's limits, and send the prompt to Ollama.
- `picks` has one local tag per memory size: the first in `prefer` that fits. The app reads the table at onboarding and every time Settings › Providers opens. A family that fails to load keeps last week's rows, marked `stale`.
