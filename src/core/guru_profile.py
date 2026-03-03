# -*- coding: utf-8 -*-
"""
名人 / 机构（大佬）持仓与变动模型。

本模块只定义数据结构，不关心数据从哪来（手工配置 / WebUI / 外部服务）。
后续由服务层（如 DebateService）读取这些结构，在 Prompt 中引导模型参考大佬行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class GuruPosition:
    """
    某位大佬在单个标的上的持仓信息。
    """

    code: str
    name: Optional[str] = None
    weight_pct: float = 0.0              # 在该大佬组合中的权重比例（%）
    latest_action: Optional[str] = None  # 最近操作：加仓/减仓/新建/清仓/不变 等
    change_pct: Optional[float] = None   # 最近一个报告期的仓位变化（百分点，如 +2.5）
    thesis: Optional[str] = None         # 公开说明或推测逻辑简述


@dataclass
class GuruPortfolioSnapshot:
    """
    单个大佬在某一时点的组合快照。
    """

    guru_name: str                        # 大佬名称，例如 “巴菲特”、“某顶级公募经理”
    style_tagline: str                    # 风格简介：价值型/成长型/量化/宏观等
    positions: Dict[str, GuruPosition]    # key 为股票代码，如 '600519' / 'AAPL'
    as_of: Optional[str] = None           # 报告期时间，如 '2025-12-31'
    notes: Optional[str] = None           # 其他备注，例如 “13F 披露数据”


@dataclass
class GuruHoldingsContext:
    """
    多位大佬的组合快照集合。
    """

    portfolios: List[GuruPortfolioSnapshot]

