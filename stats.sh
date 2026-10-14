#!/bin/sh
# MAT 下载数据：官网上「点了下载」的次数（Abacus 计数器）和安装包真正被下载的次数（GitHub release）。
# 用法： sh ~/code/MAT-website/stats.sh
# 点击：mac-download = 电脑上点了下载（zip 开始下）；phone-download = 手机上点了下载（弹出「发链接到 Mac」）。
#       每次打开页面每种最多记一次；浏览器开了「请勿追踪」不记。从 2026-10-10 v4.0 起才有。
# 下载：GitHub 自己记的 zip 下载次数，按版本列出再合计（包括我们自己核对时下的那几次）。
NS=$(grep -o "clicks:'[^']*'" "$(dirname "$0")/index.html" | head -1 | sed "s/clicks:'//; s/'//")
[ -n "$NS" ] || { echo "index.html 里 MAT_SITE.clicks 是空的：点击计数没开。"; NS=""; }
if [ -n "$NS" ]; then
  echo "官网点击（Abacus · ${NS}）"
  for k in mac-download phone-download; do
    v=$(curl -s "https://abacus.jasoncameron.dev/get/$NS/$k" | sed -n 's/.*"value":[ ]*\([0-9]*\).*/\1/p')
    printf '  %-15s %s\n' "$k" "${v:-0}"
  done
fi
echo "GitHub 下载（RobertLeeHao/MAT releases）"
curl -s "https://api.github.com/repos/RobertLeeHao/MAT/releases" | python3 -c '
import json, sys
total = 0
for r in json.load(sys.stdin):
    for a in r.get("assets", []):
        print("  %-10s %-16s %d" % (r["tag_name"], a["name"], a["download_count"]))
        total += a["download_count"]
print("  合计 %d" % total)'
