# -*- coding: utf-8 -*-
"""
组合配置加载模块（Portfolio Loader）。

职责：
1. 从 config/portfolio/*.json 中加载用户组合与观察名单配置
2. 封装为内部数据模型（PortfolioSnapshot / Watchlist），供 Round1/多轮分析复用
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.config import Config, get_config
from src.core.position_profile import PortfolioSnapshot, HoldingPosition


logger = logging.getLogger(__name__)


@dataclass
class WatchItem:
    """单个观察标的。"""

    code: str
    name: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass
class Watchlist:
    """观察名单清单。"""

    as_of: Optional[str] = None
    items: List[WatchItem] = field(default_factory=list)


def _load_json_file(path: Path) -> Optional[dict]:
    """通用 JSON 读取辅助函数。"""
    if not path.exists():
        logger.warning("组合配置文件不存在: %s", path)
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("读取组合配置文件失败: %s, error=%s", path, exc)
        return None


def load_user_portfolio(config: Optional[Config] = None) -> Optional[PortfolioSnapshot]:
    """
    从配置路径加载用户组合，构造 PortfolioSnapshot。

    Returns:
        PortfolioSnapshot 或 None（文件缺失 / 解析失败时）
    """
    cfg = config or get_config()
    path = Path(cfg.user_portfolio_path)
    data = _load_json_file(path)
    if not data:
        return None

    positions_data = data.get("positions") or []
    positions_map: dict[str, HoldingPosition] = {}

    for item in positions_data:
        try:
            code = str(item.get("code", "")).strip()
            if not code:
                continue
            pos = HoldingPosition(
                code=code,
                name=item.get("name"),
                position_pct=float(item.get("position_pct", 0) or 0),
                cost_price=item.get("cost_price"),
                notes=item.get("notes"),
            )
            # 兼容 shares 字段：如果 HoldingPosition 将来扩展 shares，可在此注入
            if hasattr(pos, "shares"):
                try:
                    setattr(pos, "shares", float(item.get("shares", 0) or 0))
                except Exception:
                    # 忽略 shares 解析错误
                    pass
            positions_map[code] = pos
        except Exception as exc:
            logger.warning("解析单个持仓失败，已跳过: item=%s, error=%s", item, exc)
            continue

    snapshot = PortfolioSnapshot(
        positions=positions_map,
        total_equity=data.get("total_equity"),
        as_of=data.get("as_of"),
        account_name=data.get("account_name"),
    )
    logger.info(
        "已从 %s 加载用户组合：account=%s, positions=%d",
        path,
        snapshot.account_name,
        len(snapshot.positions),
    )
    return snapshot


def load_watchlist(config: Optional[Config] = None) -> Optional[Watchlist]:
    """
    从配置路径加载观察名单，构造 Watchlist。
    """
    cfg = config or get_config()
    path = Path(cfg.watchlist_path)
    data = _load_json_file(path)
    if not data:
        return None

    items_data = data.get("items") or []
    items: List[WatchItem] = []

    for item in items_data:
        try:
            code = str(item.get("code", "")).strip()
            if not code:
                continue
            tags_val = item.get("tags") or []
            if isinstance(tags_val, str):
                tags = [t.strip() for t in tags_val.split(",") if t.strip()]
            else:
                tags = [str(t).strip() for t in tags_val if str(t).strip()]
            watch_item = WatchItem(
                code=code,
                name=item.get("name"),
                tags=tags,
                notes=item.get("notes"),
            )
            items.append(watch_item)
        except Exception as exc:
            logger.warning("解析观察名单条目失败，已跳过: item=%s, error=%s", item, exc)
            continue

    watchlist = Watchlist(
        as_of=data.get("as_of"),
        items=items,
    )
    logger.info(
        "已从 %s 加载观察名单：as_of=%s, items=%d",
        path,
        watchlist.as_of,
        len(watchlist.items),
    )
    return watchlist

