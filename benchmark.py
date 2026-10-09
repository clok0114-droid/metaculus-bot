"""背反検証の工程に効果があるかを、コミュニティ予測を基準に測る。

Benchmarker 自身のドキュメントが「100〜200問が出発点、100問未満では大きな差しか
判別できず、100問でも劣る側が勝つ確率が約30%ある」と書いている。だから問題数は
削らない。代わりに1問あたりの費用を削る。

- 予測は1問1本にする（Metaculus の参照スクリプトも同じ）。アンサンブルの平均化は
  別途検証済みの選択で、ここで測りたいのはプロンプトの差だから、混ぜない。
- 両者のモデルを1つに固定する。系統を回したままだと、プロンプトの差とモデルの差が
  分離できない。
- background_info は落とす。本戦の問題には詳しい背景が付いていないことが多い。

実行:
    poetry run python benchmark.py
    BENCHMARK_QUESTIONS=40 poetry run python benchmark.py   # 本数を変える
"""

from __future__ import annotations

import asyncio
import logging
import os

from bot_helpers import check_environment, silence_noisy_dependencies

silence_noisy_dependencies()

from forecasting_tools import GeneralLlm, MetaculusClient
from forecasting_tools.ai_models.resource_managers.monetary_cost_manager import (
    MonetaryCostManager,
)
from forecasting_tools.cp_benchmarking.benchmarker import Benchmarker

from main import FallTemplateBot2026

logger = logging.getLogger(__name__)

# A/B で動かす唯一の変数はプロンプトなので、モデルは固定する。
FIXED_MODEL = "openrouter/anthropic/claude-sonnet-5.5"


class _FixedModelBot(FallTemplateBot2026):
    """アンサンブルの系統回しを止め、1モデルに固定した版。"""

    def _next_ensemble_llm(self) -> GeneralLlm:
        return GeneralLlm(
            model=FIXED_MODEL,
            temperature=0.3,
            timeout=120,
            allowed_tries=2,
        )


class WithDisconfirmation(_FixedModelBot):
    """錨 → 反証 → 移動幅の正当化 を含む版（本番と同じプロンプト）。"""


class WithoutDisconfirmation(_FixedModelBot):
    """背反検証の工程だけを抜いた版。差分はこの1点のみ。"""

    @staticmethod
    def _disconfirmation_block() -> str:
        return ""


def _build(cls: type[_FixedModelBot]) -> _FixedModelBot:
    return cls(
        research_reports_per_question=1,
        predictions_per_research_report=1,
        publish_reports_to_metaculus=False,
        skip_previously_forecasted_questions=False,
        folder_to_save_reports_to=None,
    )


async def main() -> None:
    check_environment(strict=True)

    num_questions = int(os.environ.get("BENCHMARK_QUESTIONS", "100"))
    fetch_only = os.environ.get("BENCHMARK_FETCH_ONLY", "") not in ("", "0", "false")

    # 既定の get_benchmark_questions は、サーバー側で200件該当すると見積もった
    # まま、ローカルの絞り込み（コミュニティ予測の存在・bot を含まない集計・
    # 予測者30人以上）で0件になって例外を投げる。条件を緩め、足りなくても
    # 例外にせず「何件取れたか」を見てから進む形にする。
    questions = MetaculusClient().get_benchmark_questions(
        num_questions,
        num_forecasters_gte=10,
        max_days_since_opening=None,
        error_if_question_target_missed=False,
    )
    logger.info(f"Retrieved {len(questions)} usable questions (asked for {num_questions})")

    if not questions:
        print("=" * 72)
        print("使える問題が0件だった。LLM は1回も呼んでいない（費用0）。")
        print("コミュニティ予測が公開されている open な二択問題が、いま条件を")
        print("満たしていない。num_forecasters_gte をさらに下げるか、時期を変える。")
        print("=" * 72)
        return

    MIN_FOR_SIGNAL = 60
    if len(questions) < MIN_FOR_SIGNAL:
        print("=" * 72)
        print(f"警告: 取得できたのは {len(questions)} 問で、{MIN_FOR_SIGNAL} 問を下回る。")
        print("Benchmarker の注意書き（100問でも劣る側が約30%勝つ）に照らすと、")
        print("この本数の順位は結論に使えない。動作確認としてのみ扱うこと。")
        print("=" * 72)

    if fetch_only:
        print("=" * 72)
        print(f"取得のみのモード。{len(questions)} 問を取得して終了。費用0。")
        print("=" * 72)
        return

    for question in questions:
        question.background_info = None

    bots = [_build(WithDisconfirmation), _build(WithoutDisconfirmation)]

    with MonetaryCostManager() as cost_manager:
        benchmarks = await Benchmarker(
            forecast_bots=bots,
            questions_to_use=questions,
            file_path_to_save_reports="logs/forecasts/benchmarks/",
            concurrent_question_batch_size=8,
        ).run_benchmark()

        print("=" * 72)
        for benchmark in benchmarks:
            try:
                score = f"{benchmark.average_expected_baseline_score:.4f}"
            except Exception:
                score = "計算できず（予測が0件の可能性）"
            print(f"{benchmark.name}")
            print(f"  score : {score}   （高いほうが良い）")
            print(f"  cost  : ${benchmark.total_cost:.4f}")
            print(f"  time  : {benchmark.time_taken_in_minutes:.1f} 分")
        print(f"合計費用: ${cost_manager.current_usage:.4f}")
        print(f"問題数  : {len(questions)}")
        print(
            "注意: 100問でも、実力差が小さい場合は劣る側が勝つことが約30%ある。"
            "差が小さいときに順位をそのまま結論にしないこと。"
        )
        print("=" * 72)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
