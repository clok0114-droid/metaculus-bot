"""main_new.py の歯止め部分だけを、forecasting_tools 無しで検証する。

本体は import 時に forecasting_tools を要求するのでローカルでは動かない。
そこで歯止めの関数群だけを原文から切り出し、スタブを与えて動かす。
確かめるのは4点。
  1. already_forecasted が my_forecasts.latest の有無で分かれること
  2. pick_questions が未予測だけを締切の早い順に cap 件返すこと
  3. close_time が None / naive でも落ちないこと
  4. 残高ゲートの算術（affordable と cap の下げ方）
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import io
import json
import logging
import pathlib
import re
import sys
import types
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = pathlib.Path(r"main.py").read_text(encoding="utf-8")

# 歯止めブロックを原文から切り出す（改変せずそのまま exec する）
start = SRC.index("COST_PER_QUESTION = 0.235")
end = SRC.index("class FallTemplateBot2026")
block = SRC[start:end]
print(f"切り出し {len(block)} バイト / {block.count(chr(10))} 行")


class _ApiFilter:
    def __init__(self, allowed_tournaments=None, allowed_statuses=None):
        self.allowed_tournaments = allowed_tournaments
        self.allowed_statuses = allowed_statuses


ns = {
    "os": types.SimpleNamespace(getenv=lambda k: None),
    "json": json,
    "urllib": urllib,
    "logger": logging.getLogger("test"),
    "datetime": _dt.datetime,
    "timezone": _dt.timezone,
    "ApiFilter": _ApiFilter,
    "__builtins__": __builtins__,
}
exec(compile(block, "main_new.py:guards", "exec"), ns)
print("exec OK（関数:", ", ".join(k for k in ns if callable(ns[k]) and not k.startswith("_")), ")")

already_forecasted = ns["already_forecasted"]
pick_questions = ns["pick_questions"]
emit_github_output = ns["emit_github_output"]
COST = ns["COST_PER_QUESTION"]

ok = 0
bad = 0


def check(label, got, want):
    global ok, bad
    if got == want:
        ok += 1
        print(f"  ok   {label}")
    else:
        bad += 1
        print(f"  NG   {label}: got {got!r} want {want!r}")


class Q:
    def __init__(self, name, close, mine):
        self.question_text = name
        self.close_time = close
        self.api_json = {"question": {"my_forecasts": mine}}


UTC = _dt.timezone.utc


def t(day):
    return _dt.datetime(2026, 10, day, tzinfo=UTC)


print("\n1. already_forecasted")
check("latest あり → 済", already_forecasted(Q("a", t(20), {"latest": {"x": 1}})), True)
check("latest None → 未", already_forecasted(Q("b", t(20), {"latest": None})), False)
check("my_forecasts None → 未", already_forecasted(Q("c", t(20), None)), False)
check("api_json 無し → 未", already_forecasted(types.SimpleNamespace()), False)

print("\n2-3. pick_questions（締切順・cap・未予測のみ）")
pool = [
    Q("遠い未予測", t(28), None),
    Q("済み（締切最短）", t(14), {"latest": {"x": 1}}),
    Q("近い未予測", t(16), None),
    Q("close_time なし", None, None),
    Q("naive な close_time", _dt.datetime(2026, 10, 15), None),
]


class FakeClient:
    def __init__(self, by_tid):
        self.by_tid = by_tid
        self.asked = []

    async def get_questions_matching_filter(self, flt, error_if_question_target_missed=True):
        tid = flt.allowed_tournaments[0]
        self.asked.append((tid, flt.allowed_statuses))
        if self.by_tid[tid] is None:
            raise RuntimeError("取得失敗を模擬")
        return self.by_tid[tid]


client = FakeClient({"T1": pool})
got = asyncio.run(pick_questions(client, ["T1"], 3))
check("cap 3 で 3 件", len(got), 3)
check(
    "締切の早い順・未予測のみ",
    [q.question_text for q in got],
    ["naive な close_time", "近い未予測", "遠い未予測"],
)
check("open だけを要求している", client.asked, [("T1", ["open"])])

got = asyncio.run(pick_questions(FakeClient({"T1": pool}), ["T1"], 0))
check("cap 0 は全件（未予測 4 件）", len(got), 4)
check("close_time なしは最後", got[-1].question_text, "close_time なし")

got = asyncio.run(pick_questions(FakeClient({"T1": None, "T2": pool}), ["T1", "T2"], 2))
check("片方が例外でも続行する", [q.question_text for q in got], ["naive な close_time", "近い未予測"])

got = asyncio.run(pick_questions(FakeClient({"T1": []}), ["T1"], 5))
check("空なら空", got, [])

print("\n4. 残高ゲートの算術")


def gate(balance, min_credits, max_questions):
    """main_new.py のゲートと同じ式。stop なら None を返す。"""
    cap = max_questions
    if balance is None:
        return cap
    if min_credits > 0:
        affordable = int((balance - min_credits) / COST)
        if affordable <= 0:
            return None
        if cap <= 0 or affordable < cap:
            cap = affordable
    return cap


check("残高21.11 下限1.00 上限8 → 8", gate(21.11, 1.00, 8), 8)
check("残高2.00 下限1.00 上限8 → 4 に下がる", gate(2.00, 1.00, 8), 4)
check("残高1.20 下限1.00 上限8 → 0 問は払えず停止", gate(1.20, 1.00, 8), None)
check("残高1.00 下限1.00 → 停止", gate(1.00, 1.00, 8), None)
check("残高0.50 下限1.00 → 停止", gate(0.50, 1.00, 8), None)
check("残高21.11 上限0（無制限）→ 85 に制限", gate(21.11, 1.00, 0), 85)
check("下限0 なら残高で絞らない", gate(0.10, 0.0, 8), 8)
check("照会できない（None）なら上限のみ", gate(None, 1.00, 8), 8)

print("\n5. emit_github_output")
tmp = pathlib.Path(r"/tmp/gh_out_test.txt")
tmp.parent.mkdir(parents=True, exist_ok=True)
tmp.write_text("", encoding="utf-8")
ns["os"] = types.SimpleNamespace(getenv=lambda k: str(tmp) if k == "GITHUB_OUTPUT" else None)
exec(compile(block, "main_new.py:guards", "exec"), ns)
ns["emit_github_output"](proceed="true", hit_cap="false", forecasted="3", remaining="20.17")
written = tmp.read_text(encoding="utf-8")
check(
    "1行1組で書く",
    written,
    "proceed=true\nhit_cap=false\nforecasted=3\nremaining=20.17\n",
)
ns["os"] = types.SimpleNamespace(getenv=lambda k: None)
exec(compile(block, "main_new.py:guards", "exec"), ns)
ns["emit_github_output"](proceed="true")
check("GITHUB_OUTPUT が無ければ何もしない（例外を出さない）", True, True)

print(f"\n{'=' * 60}\n合格 {ok} / 失敗 {bad}")
sys.exit(1 if bad else 0)
