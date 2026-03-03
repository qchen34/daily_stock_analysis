# -*- coding: utf-8 -*-
"""
个人持仓信息与仓位分档模型。

本模块只定义数据结构和基础工具函数，不直接访问数据库或外部服务。
上层可以从 WebUI、配置或账户数据构造 PortfolioSnapshot，再传给分析/辩论模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from src.core.debate_profile import PositionBucket, bucket_position


@dataclass
class HoldingPosition:
    """
    单个标的的持仓信息。
    
    - code: 股票/标的代码，例如 '600519', 'AAPL'
    - name: 可选名称，便于展示
    - position_pct: 静态配置的仓位百分比（0-100），用于没有动态计算时的回退
    - cost_price: 成本价（可选，用于以后做盈亏分析）
    - notes: 备注，例如“长线持有”、“短线试仓”等
    - shares: 持有数量（股数/份额），用于结合实时价格计算市值
    - runtime_price: 运行时获取的最新价格（不写回配置）
    - runtime_market_value: 运行时计算的市值（shares * runtime_price）
    - runtime_position_pct: 运行时计算的仓位百分比（相对 total_equity）
    """
    
    code: str
    name: Optional[str] = None
    position_pct: float = 0.0
    cost_price: Optional[float] = None
    notes: Optional[str] = None
    shares: Optional[float] = None
    runtime_price: Optional[float] = None
    runtime_market_value: Optional[float] = None
    runtime_position_pct: Optional[float] = None


@dataclass
class PortfolioSnapshot:
    """
    某一时刻的整体持仓快照（组合视图）。

    这里只关心“结构化持仓信息”，不关心数据来源。
    """

    positions: Dict[str, HoldingPosition]
    total_equity: Optional[float] = None  # 总资产（可选）
    as_of: Optional[str] = None  # 快照时间（例如 '2026-02-25'）
    account_name: Optional[str] = None  # 账户名称/别名

    def get_position(self, code: str) -> Optional[HoldingPosition]:
        """
        获取某个代码的持仓信息（大小写不敏感），若无持仓则返回 None。
        """
        if not self.positions:
            return None

        # 优先精确匹配
        if code in self.positions:
            return self.positions[code]

        # 次选大小写不敏感匹配
        code_lower = code.lower()
        for k, pos in self.positions.items():
            if k.lower() == code_lower:
                return pos
        return None


def get_position_for_code(
    portfolio: Optional[PortfolioSnapshot],
    code: str,
) -> Optional[HoldingPosition]:
    """
    根据股票代码获取当前持仓信息（若无持仓或无组合信息则返回 None）。
    """
    if portfolio is None or not code:
        return None
    return portfolio.get_position(code)


def get_position_pct_for_code(
    portfolio: Optional[PortfolioSnapshot],
    code: str,
) -> float:
    """
    获取某只股票的仓位百分比，未持有则返回 0.0。
    """
    pos = get_position_for_code(portfolio, code)
    if pos is None:
        return 0.0

    # 优先使用运行时动态计算的仓位（如果已经填充）
    value = getattr(pos, "runtime_position_pct", None)
    if value is None:
        value = pos.position_pct

    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def describe_position_bucket(position_pct: float) -> Tuple[PositionBucket, str]:
    """
    将精确仓位映射到仓位档位，并返回一段人类可读的描述。

    示例：
        0   -> (EMPTY,  '当前在该标的上空仓')
        15  -> (LIGHT,  '当前是轻仓（约15%）')
        45  -> (MEDIUM, '当前是中等仓位（约45%）')
        80  -> (HEAVY,  '当前是重仓（约80%）')
    """
    bucket = bucket_position(position_pct)
    try:
        v = max(0.0, float(position_pct))
    except (TypeError, ValueError):
        v = 0.0

    if bucket == PositionBucket.EMPTY:
        desc = "当前在该标的上空仓（0% 仓位）"
    elif bucket == PositionBucket.LIGHT:
        desc = f"当前是轻仓（约 {v:.1f}% 仓位）"
    elif bucket == PositionBucket.MEDIUM:
        desc = f"当前是中等仓位（约 {v:.1f}% 仓位）"
    else:
        desc = f"当前是重仓（约 {v:.1f}% 仓位）"

    return bucket, desc

