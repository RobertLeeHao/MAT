#!/bin/sh
# The weekly rebuild: fetch → build → check and compare → publish.
#   sh rankings/pipeline/run.sh
# Writes rankings/data/<date>/sources.json and rankings/v2/changes/<date>.md every time;
# rankings/v2/latest.json and rankings/v2/archive/<date>.json only when the checks pass.
set -e
R="$(cd "$(dirname "$0")/.." && pwd)"
P="$R/pipeline"
D="${RANKINGS_DATE:-$(date -u +%F)}"
PY="${PYTHON:-python3}"
FETCH="${FETCH_CMD:-$PY $P/fetch.py}"

PREV_DIR="$(ls -d "$R"/data/*/ 2>/dev/null | grep -v "/$D/\$" | sort | tail -1)"
PREV_SRC="${PREV_DIR}sources.json"
mkdir -p "$R/data/$D" "$R/v2/archive" "$R/v2/changes"

if [ -f "$PREV_SRC" ]; then $FETCH --out "$R/data/$D/sources.json" --previous "$PREV_SRC"
else $FETCH --out "$R/data/$D/sources.json"; PREV_SRC=""; fi

TMP="$R/v2/.candidate.json"
$PY "$P/build.py" --sources "$R/data/$D/sources.json" --out "$TMP"

OLD=""; [ -f "$R/v2/latest.json" ] && OLD="--old $R/v2/latest.json"
OSRC=""; [ -n "$PREV_SRC" ] && OSRC="--old-sources $PREV_SRC"
if $PY "$P/diff.py" --new "$TMP" $OLD --sources "$R/data/$D/sources.json" $OSRC --out "$R/v2/changes/$D.md"; then
  mv "$TMP" "$R/v2/archive/$D.json"
  cp "$R/v2/archive/$D.json" "$R/v2/latest.json"
  $PY - "$R/v2" "$D" <<'PYEOF'
import json, os, sys
v2, d = sys.argv[1], sys.argv[2]
dates = sorted((f[:-5] for f in os.listdir(os.path.join(v2, "archive")) if f.endswith(".json")), reverse=True)
json.dump({"latest": d, "latestUrl": "latest.json", "archive": [{"date": x, "url": f"archive/{x}.json", "changes": f"changes/{x}.md"} for x in dates]},
          open(os.path.join(v2, "index.json"), "w"), indent=1)
PYEOF
  echo "published=true" >> "${GITHUB_OUTPUT:-/dev/null}"
  echo "✅ published $D"
else
  rm -f "$TMP"
  echo "published=false" >> "${GITHUB_OUTPUT:-/dev/null}"
  echo "⛔ checks failed; see rankings/v2/changes/$D.md"
fi
