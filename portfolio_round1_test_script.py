# -*- coding: utf-8 -*-
"""
组合第一轮分析自测脚本。

用法（在 daily_stock_analysis 目录下）：
    pip install -r requirements.txt
    python portfolio_round1_test_script.py

脚本逻辑：
1. 从 user_portfolio.json 读取个人组合（PortfolioSnapshot）
2. 可选：从 guru_holdings.json 读取大佬组合（GuruHoldingsContext）
3. 调用 PortfolioAnalysisService.analyze_portfolio()
4. 将大模型输出打印到终端，便于快速调 Prompt
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.core.position_profile import HoldingPosition, PortfolioSnapshot
from src.core.guru_profile import GuruHoldingsContext, GuruPortfolioSnapshot, GuruPosition
from src.services.portfolio_analysis_service import PortfolioAnalysisService


logger = logging.getLogger(__name__)


def _load_portfolio_from_json(path: str) -> Optional[PortfolioSnapshot]:
    if not os.path.exists(path):
        logger.error("未找到组合配置文件：%s", path)
        return None

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    positions: Dict[str, HoldingPosition] = {}
    for p in raw.get("positions", []):
        code = p.get("code")
        if not code:
            continue
        positions[code] = HoldingPosition(
            code=code,
            name=p.get("name"),
            position_pct=p.get("position_pct", 0.0),
            cost_price=p.get("cost_price"),
            notes=p.get("notes"),
            shares=p.get("shares"),
        )

    snapshot = PortfolioSnapshot(
        positions=positions,
        total_equity=raw.get("total_equity"),
        as_of=raw.get("as_of"),
        account_name=raw.get("account_name"),
    )
    return snapshot


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

    portfolio_path = os.path.join(cwd, "user_portfolio.json")
    guru_path = os.path.join(cwd, "guru_holdings.json")

    portfolio = _load_portfolio_from_json(portfolio_path)
    if portfolio is None:
        logger.error("无法加载组合信息，退出。")
        return 1

    guru_context = _load_guru_context_from_json(guru_path)

    service = PortfolioAnalysisService()
    result = service.analyze_portfolio(portfolio, guru_context=guru_context)
    if not result:
        logger.error("组合第一轮分析未返回结果，请检查 LLM 配置。")
        return 1

    print("\n" + "=" * 80)
    print("组合第一轮分析输出：")
    print("=" * 80 + "\n")
    print(result.raw_text)
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
        f.write(result.raw_text)
    logger.info("组合第一轮分析结果已保存到: %s", out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

