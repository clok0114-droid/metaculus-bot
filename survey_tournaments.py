"""今どのトーナメントに open の問題があるかを数える。LLM は呼ばない＝費用0。

count_open.py は本戦（SDK 定数 id=33022）も MiniBench も open 0 問を返した。
一方 slug `fall-futureeval-2026` には open の投稿がある。SDK 定数が古い ID を
指している疑いがあるので、slug 側から数えて突き合わせる。

直した点（最初の版の欠陥）
  - `limit=1` で数えていたので「1」は件数ではなく「1 件以上」の意味だった
  - 1 候補につき 3 回叩いて 429 を踏んだ。1 回に減らし、間隔を空ける
  - `/api/tournaments/` は 404。`/api/projects/tournaments/` を試す
"""
from __future__ import annotations

import json
import os
import sys
import time
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
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(8 * (attempt + 1))
                continue
            return {"_error": f"HTTP {exc.code}",
                    "_body": exc.read()[:160].decode("utf-8", "replace")}
    return {"_error": "429 が続いた"}


print("=" * 78)
print("1) トーナメント一覧の場所を探す")
for path in ("/projects/tournaments/", "/tournaments/", "/projects/"):
    data = get(path, limit=100)
    # 一覧は辞書（results 入り）でもリストでも返る。エラーは辞書の _error のみ。
    if isinstance(data, dict) and "_error" in data:
        print(f"   {path:<28} {data['_error']}")
        time.sleep(2)
        continue
    rows = data if isinstance(data, list) else data.get("results", [])
    rows = [r for r in rows if isinstance(r, dict)]
    print(f"   {path:<28} ok  {len(rows)} 件")
    for item in rows:
        slug = str(item.get("slug") or "")
        name = str(item.get("name") or "")
        if any(k in (slug + name).lower()
               for k in ("bench", "bot", "eval", "aib", "pulse", "cup")):
            print(f"      id={str(item.get('id')):<8} slug={slug[:34]:<34} "
                  f"{name[:32]:<32} close={str(item.get('close_date'))[:10]}")
    break

CANDIDATES = [
    "fall-futureeval-2026",
    "minibench",
    "market-pulse-26q4",
    "metaculus-cup-fall-2026",
    "bot-testing-area",
    "33022",
]

print("\n2) 候補ごとの open 問題数（limit=100 で実数を数える）")
detail = {}
for slug in CANDIDATES:
    result = get("/posts/", tournaments=slug, statuses="open", limit=100,
                 order_by="scheduled_close_time")
    time.sleep(3)
    if "_error" in result:
        print(f"   {slug:<26} {result['_error']} {result.get('_body', '')[:60]}")
        continue
    posts = result.get("results", [])
    reported = result.get("count")
    detail[slug] = posts
    print(f"   {slug:<26} open {len(posts):>3} 件"
          + (f"（API の count {reported}）" if reported is not None else ""))

print("\n3) open の中身（締切の早い順・自分の予測の有無つき）")
for slug, posts in detail.items():
    if not posts:
        continue
    mine_done = 0
    print(f"\n   --- {slug}  {len(posts)} 件 ---")
    for post in posts:
        question = post.get("question") or {}
        forecasts = question.get("my_forecasts") or {}
        done = forecasts.get("latest") is not None
        mine_done += done
        if len(posts) <= 30 or not done:
            print(f"      {'済' if done else '未'}  "
                  f"close={str(question.get('scheduled_close_time'))[:16]:<16} "
                  f"type={str(question.get('type'))[:12]:<12} "
                  f"{str(post.get('title'))[:46]}")
    todo = len(posts) - mine_done
    print(f"      → 済 {mine_done} / 未 {todo}  "
          f"未の概算 ${todo * 0.235:.2f}（$0.235/問）")
print("=" * 78)
