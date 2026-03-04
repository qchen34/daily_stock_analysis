# -*- coding: utf-8 -*-
"""
组合第一轮分析自测脚本（Round1 JSON + Markdown 验证）。

用法（在 daily_stock_analysis 目录下）：
    pip install -r requirements.txt
    python portfolio_round1_test_script.py

脚本逻辑：
1. 通过 Config + portfolio_loader 从 config/portfolio/user_portfolio.json 读取个人组合（PortfolioSnapshot）
2. 通过 portfolio_loader 从 config/portfolio/watchlist.json 读取观察名单（Watchlist）
3. 可选：从 guru_holdings.json 读取大佬组合（GuruHoldingsContext）
4. 调用 PortfolioAnalysisService.analyze_portfolio()
5. 在终端打印 Round1 的 JSON 原始输出预览与 Markdown 渲染结果
6. 将 Markdown 版本保存到 reports 目录，便于与 Round2/3/4 对齐
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.config import get_config
from src.core.position_profile import PortfolioSnapshot
from src.core.guru_profile import GuruHoldingsContext, GuruPortfolioSnapshot, GuruPosition
from src.services.portfolio_analysis_service import PortfolioAnalysisService
from src.services.portfolio_loader import load_user_portfolio, load_watchlist


logger = logging.getLogger(__name__)


def _load_portfolio_via_loader() -> Optional[PortfolioSnapshot]:
    """使用 Config + portfolio_loader 加载用户组合。"""
    config = get_config()
    return load_user_portfolio(config)


def _load_guru_context_from_json(path: str) -> Optional[GuruHoldingsContext]:
    if not os.path.exists(path):
        logger.info("未找到 guru_holdings.json，将不传入大佬组合上下文。")
        return None

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    portfolios = []
    for snap in raw.get("portfolios", []):
        pos_map: Dict[str, GuruPosition] = {}
        for p in snap.get("positions", []):
            code = p.get("code")
            if not code:
                continue
            pos_map[code] = GuruPosition(
                code=code,
                name=p.get("name"),
                weight_pct=p.get("weight_pct", 0.0),
                latest_action=p.get("latest_action"),
                change_pct=p.get("change_pct"),
                thesis=p.get("thesis"),
            )
        portfolios.append(
            GuruPortfolioSnapshot(
                guru_name=snap.get("guru_name", "未知大佬"),
                style_tagline=snap.get("style_tagline", ""),
                positions=pos_map,
                as_of=snap.get("as_of"),
                notes=snap.get("notes"),
            )
        )

    if not portfolios:
        return None
    return GuruHoldingsContext(portfolios=portfolios)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    cwd = os.getcwd()
    logger.info("当前工作目录: %s", cwd)

    guru_path = os.path.join(cwd, "guru_holdings.json")

    portfolio = _load_portfolio_via_loader()
    if portfolio is None:
        logger.error("无法加载组合信息，退出。")
        return 1

    guru_context = _load_guru_context_from_json(guru_path)

    service = PortfolioAnalysisService()
    watchlist = load_watchlist(get_config())
    result = service.analyze_portfolio(
        portfolio,
        guru_context=guru_context,
        watchlist=watchlist,
    )
    if not result:
        logger.error("组合第一轮分析未返回结果，请检查 LLM 配置。")
        return 1

    print("\n" + "=" * 80)
    print("组合第一轮分析 JSON 原始输出预览（raw_text）：")
    print("=" * 80 + "\n")
    preview = result.raw_text[:800] + "..." if len(result.raw_text) > 800 else result.raw_text
    print(preview)
    print("\n" + "=" * 80)

    print("\n" + "=" * 80)
    print("组合第一轮分析 Markdown 渲染结果：")
    print("=" * 80 + "\n")
    markdown = result.to_markdown()
    print(markdown)
    print("\n" + "=" * 80)

    # 将结果保存到 reports 目录（优先使用本次运行的子目录）
    reports_root_env = os.getenv("REPORTS_RUN_DIR")
    if reports_root_env:
        reports_dir = Path(reports_root_env)
    else:
        reports_dir = Path(cwd) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"portfolio_round1_{ts}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info("组合第一轮分析结果 (Markdown) 已保存到: %s", out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

