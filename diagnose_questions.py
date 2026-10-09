"""既に投稿した予測のうち、答えが出たものを採点する。

「解決済み問題で retro 採点すれば $0」は誤り。解決済み問題に予測させるには
LLM 呼び出しが要る。本当に $0 なのは「既に投稿済みの予測」を答え合わせする
場合だけ。まずその素材があるかを確定させる。

見るもの:
  ・解決済みの問題に、このbotの予測が載っているか
  ・載っていれば、予測値と実際の結果
LLM は呼ばない。費用0。
"""

from __future__ import annotations

import asyncio
import logging

from bot_helpers import silence_noisy_dependencies

silence_noisy_dependencies()

from forecasting_tools.helpers.metaculus_client import ApiFilter, MetaculusClient

logger = logging.getLogger(__name__)

TARGETS = [
    ("bot-testing-area", "bot-testing-area"),
    ("Fall 2026 本戦", "fall-futureeval-2026"),
    ("Fall 2026 数値ID", 33022),
    ("MiniBench", "minibench"),
    ("Market Pulse 26q4", "market-pulse-26q4"),
]


def my_forecast(question) -> object | None:
    """このアカウントの予測を取り出す。無ければ None。"""
    api_json = getattr(question, "api_json", None) or {}
    inner = api_json.get("question") or {}
    mine = inner.get("my_forecasts")
    if not isinstance(mine, dict):
        return None
    return mine.get("latest")


async def main() -> None:
    client = MetaculusClient()
    print("=" * 82)
    total_with_forecast = 0
    for label, tid in TARGETS:
        for status in ("resolved", "closed"):
            try:
                questions = await client.get_questions_matching_filter(
                    ApiFilter(
                        allowed_tournaments=[tid],
                        allowed_statuses=[status],
                        group_question_mode="unpack_subquestions",
                    ),
                    error_if_question_target_missed=False,
                )
            except Exception as exc:
                print(f"  {label:<20} {status:<9} ERR {type(exc).__name__}")
                continue

            mine = [q for q in questions if my_forecast(q) is not None]
            total_with_forecast += len(mine)
            print(f"  {label:<20} {status:<9} 全{len(questions):>4}問 / "
                  f"自分の予測あり {len(mine):>4}問")
            for q in mine[:5]:
                latest = my_forecast(q)
                resolution = getattr(q, "resolution", None)
                keys = sorted(latest.keys())[:6] if isinstance(latest, dict) else latest
                print(f"      resolution={str(resolution)[:18]:<18} my={str(keys)[:70]}")
    print("=" * 82)
    print(f"  採点できる素材（自分の予測がある解決済み/終了問題）: {total_with_forecast} 問")
    if total_with_forecast == 0:
        print("  → $0 で測れる素材は無い。精度測定には LLM 呼び出しの費用が要る。")
    print("=" * 82)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
