"""どの環境変数がワークフローに届いているかを確認する。値は表示しない。

AskNews の鍵を設定したはずなのに、実行ログに 2 系統目の区切りが出なかった。
原因は「名前の不一致」「Secrets ではなく Variables に入れた」「別リポジトリに
入れた」のいずれかが多い。長さと先頭 2 文字だけ出して、到達の有無を確定させる。

LLM は呼ばない。費用0。
"""

from __future__ import annotations

import os

NAMES = [
    "METACULUS_TOKEN",
    "OPENROUTER_API_KEY",
    "ASKNEWS_CLIENT_ID",
    "ASKNEWS_SECRET",
    "ASKNEWS_CLIENT_SECRET",
    "ASKNEWS_API_KEY",
    "PERPLEXITY_API_KEY",
    "EXA_API_KEY",
    "SERPER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
]

print("=" * 66)
print("  変数名                        到達  長さ  先頭")
print("-" * 66)
for name in NAMES:
    raw = os.environ.get(name)
    if raw is None:
        print(f"  {name:<28} 未設定   -     -")
    elif raw == "":
        print(f"  {name:<28} 空文字   0     -")
    else:
        print(f"  {name:<28} 到達   {len(raw):>3}   {raw[:2]}…")
print("=" * 66)
print("  『未設定』『空文字』は、ワークフローに値が渡っていないことを意味する。")
print("  Secrets の名前が違う／Variables 側に入っている／別リポジトリ、のどれか。")
print("=" * 66)
