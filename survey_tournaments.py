"""今どのトーナメントに open の問題があるかを数える。LLM は呼ばない＝費用0。

count_open.py が本戦も MiniBench も open 0 問を返したので、季節の切れ目なのか
トーナメント ID が回ったのかを切り分ける。Metaculus の API は未認証だと 403 な
ので、ジョブの中から METACULUS_TOKEN を付けて叩く。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["METACULUS_TOKEN"]
BASE = "https://www.metaculus.com/api"


def get(path: str, **params):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "Authorization": f"Token {TOKEN}",
        "Accept": "application/json",
        "User-Agent": "survey",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"_error": f"HTTP {exc.code}", "_body": exc.read()[:300].decode("utf-8", "replace")}


print("=" * 78)
print("1) ボット向けのトーナメント一覧")
data = get("/tournaments/")
rows = data.get("results", data) if isinstance(data, dict) else data
if isinstance(data, dict) and "_error" in data:
    print("   ", data["_error"], data["_body"])
    rows = []
print(f"   {len(rows)} 件")
interesting = []
for item in rows if isinstance(rows, list) else []:
    slug = str(item.get("slug") or "")
    name = str(item.get("name") or "")
    blob = (slug + " " + name).lower()
    if any(k in blob for k in ("bench", "bot", "eval", "aib", "pulse", "cup", "ai")):
        interesting.append(item)
for item in interesting:
    print(f"      id={str(item.get('id')):<8} {str(item.get('slug'))[:34]:<34} "
          f"{str(item.get('name'))[:34]:<34} "
          f"close={str(item.get('close_date'))[:10]} prize={item.get('prize_pool')}")

print("\n2) 候補ごとの open 問題数")
candidates = []
for item in interesting:
    candidates.append(str(item.get("slug") or item.get("id")))
for extra in ("minibench", "fall-futureeval-2026", "market-pulse-26q4",
              "metaculus-cup-fall-2026", "bot-testing-area", "33022", "32828"):
    if extra not in candidates:
        candidates.append(extra)

for slug in candidates:
    result = get("/posts/", tournaments=slug, statuses="open", limit=1)
    if "_error" in result:
        print(f"   {slug:<34} {result['_error']}")
        continue
    total = result.get("count", len(result.get("results", [])))
    closed = get("/posts/", tournaments=slug, statuses="closed", limit=1)
    resolved = get("/posts/", tournaments=slug, statuses="resolved", limit=1)
    print(f"   {slug:<34} open {str(total):>4}   "
          f"closed {str(closed.get('count', '?')):>4}   "
          f"resolved {str(resolved.get('count', '?')):>4}")

print("\n3) open があるものの中身（締切の早い順に 10 件）")
for slug in candidates:
    result = get("/posts/", tournaments=slug, statuses="open", limit=10,
                 order_by="scheduled_close_time")
    if "_error" in result or not result.get("results"):
        continue
    print(f"\n   --- {slug} ---")
    for post in result["results"][:10]:
        question = post.get("question") or {}
        mine = question.get("my_forecasts") or {}
        has = "済" if mine.get("latest") else "未"
        print(f"      {has}  close={str(question.get('scheduled_close_time'))[:16]:<16} "
              f"{str(post.get('title'))[:52]}")
print("=" * 78)
