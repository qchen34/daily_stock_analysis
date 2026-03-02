# -*- coding: utf-8 -*-
"""
调试脚本：演示个人持仓模型与仓位分档描述。

在 daily_stock_analysis 目录下执行：

    python debug_position_profile.py
"""

from __future__ import annotations

from pprint import pprint

from src.core.debate_profile import PositionBucket
from src.core.position_profile import (
    HoldingPosition,
    PortfolioSnapshot,
    describe_position_bucket,
    get_position_for_code,
    get_position_pct_for_code,
)


def build_sample_portfolio() -> PortfolioSnapshot:
    """构造一个示例组合，便于本地调试。"""
    positions = {
        "600519": HoldingPosition(
            code="600519",
            name="贵州茅台",
            position_pct=25.0,
            cost_price=1500.0,
            notes="核心长期持仓",
        ),
        "AAPL": HoldingPosition(
            code="AAPL",
            name="Apple Inc.",
            position_pct=5.0,
            cost_price=180.0,
            notes="美股试仓",
        ),
        "TSLA": HoldingPosition(
            code="TSLA",
            name="Tesla Inc.",
            position_pct=0.0,
            cost_price=None,
            notes="观望中，无持仓",
        ),
    }
    return PortfolioSnapshot(
        positions=positions,
        total_equity=None,
        as_of=None,
        account_name="示例账户",
    )


def main() -> None:
    portfolio = build_sample_portfolio()
    codes_to_check = ["600519", "AAPL", "TSLA", "MSFT"]

    print("=== 示例组合持仓 ===")
    pprint(portfolio)

    print("\n=== 仓位分档与描述 ===")
    for code in codes_to_check:
        pct = get_position_pct_for_code(portfolio, code)
        bucket, desc = describe_position_bucket(pct)
        pos = get_position_for_code(portfolio, code)
        name = pos.name if pos and pos.name else code
        print("-" * 60)
        print(f"标的: {name} ({code})")
        print(f"原始 position_pct: {pct}")
        print(f"仓位档位: {bucket.value} ({PositionBucket(bucket).name})")
        print(f"描述: {desc}")


if __name__ == "__main__":
    main()

