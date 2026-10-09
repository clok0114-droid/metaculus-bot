"""1回の `--mode tournament` が何問に課金するかを、課金せずに数える。

tournament モードは FutureEval と MiniBench の両方を回す。既予測は飛ばす
設定（skip_previously_forecasted_questions=True）なので、実際に費用が
かかるのは「open かつ自分の予測がまだ無い問題」だけ。その数を出す。

LLM は呼ばない。費用0。
"""

from __future__ import annotations

import asyncio
import logging

from forecasting_tools.helpers.metaculus_client import ApiFilter, MetaculusClient

logger = logging.getLogger(__name__)


def already_forecasted(question) -> bool:
    api_json = getattr(question, "api_json", None) or {}
    inner = api_json.get("question") or {}
    mine = inner.get("my_forecasts")
    return isinstance(mine, dict) and mine.get("latest") is not None


async def main() -> None:
    client = MetaculusClient()
    targets = [
        ("FutureEval 本戦", client.CURRENT_AI_COMPETITION_ID),
        ("MiniBench", client.CURRENT_MINIBENCH_ID),
    ]
    print("=" * 76)
    grand_total = 0
    for label, tid in targets:
        try:
            questions = await client.get_questions_matching_filter(
                ApiFilter(allowed_tournaments=[tid], allowed_statuses=["open"]),
                error_if_question_target_missed=False,
            )
        except Exception as exc:
            print(f"  {label:<18} ERR {type(exc).__name__}: {exc}")
            continue
        done = [q for q in questions if already_forecasted(q)]
        todo = [q for q in questions if not already_forecasted(q)]
        grand_total += len(todo)
        print(f"  {label:<18} id={str(tid):<22} open {len(questions):>3} 問  "
              f"済 {len(done):>3}  未 {len(todo):>3}")
        for q in todo[:8]:
            close = getattr(q, "close_time", None)
            print(f"      未予測: close={str(close)[:16]}  "
                  f"{str(getattr(q, 'question_text', ''))[:52]}")
    print("-" * 76)
    print(f"  次の1回で課金される問題数: {grand_total}")
    # 実測の単価: Market Pulse で 19 問 / $4.47 = 約 $0.235 / 問
    print(f"  実測単価 $0.235/問 で概算: ${grand_total * 0.235:.2f}")
    print("=" * 76)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
