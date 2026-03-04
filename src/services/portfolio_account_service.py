# -*- coding: utf-8 -*-
"""
个人投资账户绩效服务。

职责：
1. 基于 DatabaseManager 中的 PortfolioAccountSnapshot 序列，计算账户层面的简单绩效指标
2. 为 Round1 Prompt 提供结构化的绩效上下文（如收益率、最大回撤、快照数量等）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from src.storage import get_db, PortfolioAccountSnapshot


logger = logging.getLogger(__name__)


@dataclass
class PortfolioAccountPerformance:
    """
    账户绩效概览（基于一段时间内的快照序列粗略计算）。
    """

    account_name: str
    base_currency: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    start_equity: Optional[float]
    end_equity: Optional[float]
    total_return_pct: Optional[float]
    max_drawdown_pct: Optional[float]
    snapshot_count: int


class PortfolioAccountService:
    """
    账户绩效服务。
    """

    def __init__(self) -> None:
        self._db = get_db()

    def get_performance_for_account(
        self,
        account_name: str,
        days: int = 365,
    ) -> Optional[PortfolioAccountPerformance]:
        """
        基于历史快照粗略计算账户绩效。

        - 如果快照少于 2 条，只返回最后一条的静态信息（无收益率/回撤）。
        """
        if not account_name:
            return None

        snapshots: List[PortfolioAccountSnapshot] = self._db.get_account_snapshots(
            account_name=account_name,
            days=days,
            limit=days,
        )
        if not snapshots:
            return None

        # 按时间升序排序（get_account_snapshots 已经按升序返回，这里再保险一次）
        snapshots = sorted(snapshots, key=lambda s: s.as_of)

        start = snapshots[0]
        end = snapshots[-1]
        start_eq = start.total_equity
        end_eq = end.total_equity

        total_return_pct: Optional[float] = None
        if start_eq and end_eq and start_eq > 0:
            total_return_pct = (end_eq - start_eq) / start_eq * 100.0

        # 计算最大回撤（基于 total_equity 简单计算）
        max_drawdown_pct: Optional[float] = None
        if len(snapshots) >= 2:
            peak = start_eq or 0.0
            max_dd = 0.0
            for snap in snapshots:
                eq = snap.total_equity or 0.0
                if eq > peak:
                    peak = eq
                if peak > 0:
                    dd = (eq - peak) / peak * 100.0
                    if dd < max_dd:
                        max_dd = dd
            max_drawdown_pct = max_dd

        base_currency = None
        # 这里暂时无法直接拿到账户的 base_currency，如有需要可以在 DB 中 join PortfolioAccount

        perf = PortfolioAccountPerformance(
            account_name=account_name,
            base_currency=base_currency,
            start_date=start.as_of.isoformat() if isinstance(start.as_of, datetime) else None,
            end_date=end.as_of.isoformat() if isinstance(end.as_of, datetime) else None,
            start_equity=start_eq,
            end_equity=end_eq,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            snapshot_count=len(snapshots),
        )

        return perf

