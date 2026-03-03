# -*- coding: utf-8 -*-
"""
组合第三轮决策自测脚本。

用法（在 daily_stock_analysis 目录下）：
    # 建议先跑一遍 main.py，确保本次运行的 reports 子目录已创建
    python main.py
    python portfolio_round1_test_script.py   # 生成第一轮组合分析
    python portfolio_round3_test_script.py   # 基于前两轮输出生成第三轮决策

脚本逻辑：
1. 确定本次运行使用的 reports 目录：
   - 优先使用环境变量 REPORTS_RUN_DIR（由 main.py 设置）
   - 否则退回到 ./reports 下，选最新的时间戳子目录或根目录
2. 在该目录下查找：
   - 最新的 portfolio_round1_*.md 作为第一轮输入
   - 最新的 combined_report_*.md 作为第二轮输入（若不存在，则退回到 report_*.md）
3. 调用 PortfolioDecisionService.synthesize_decision()
4. 打印第三轮输出，并保存为 round3_decision_*.md 到同一目录
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.services.portfolio_decision_service import PortfolioDecisionService


logger = logging.getLogger(__name__)


def _pick_latest(pattern: str, directory: Path) -> Optional[Path]:
    """在 directory 中按通配符 pattern 选出修改时间最新的文件。"""
    candidates = list(directory.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _resolve_reports_dir(cwd: Path) -> Path:
    """根据 REPORTS_RUN_DIR 或 reports 子目录推断本次使用的 reports 目录。"""
    env_dir = os.getenv("REPORTS_RUN_DIR")
    if env_dir:
        d = Path(env_dir)
        logger.info("使用 REPORTS_RUN_DIR 指定的目录: %s", d)
        return d

    # 没有环境变量时：尝试在 ./reports 下找到最新的时间戳子目录
    root = cwd / "reports"
    if not root.exists():
        logger.warning("reports 目录不存在，将尝试创建: %s", root)
        root.mkdir(parents=True, exist_ok=True)
        return root

    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if not subdirs:
        logger.info("reports 下暂无子目录，直接使用根目录: %s", root)
        return root

    latest = max(subdirs, key=lambda p: p.stat().st_mtime)
    logger.info("未设置 REPORTS_RUN_DIR，使用最新子目录: %s", latest)
    return latest


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    cwd = Path(os.getcwd())
    logger.info("当前工作目录: %s", cwd)

    reports_dir = _resolve_reports_dir(cwd)

    # 第一轮：portfolio_round1_*.md
    round1_path = _pick_latest("portfolio_round1_*.md", reports_dir)
    if not round1_path:
        logger.error("在 %s 下未找到 portfolio_round1_*.md，请先运行第一轮组合分析脚本。", reports_dir)
        return 1

    # 第二轮：优先使用 combined_report_*.md，若无则退回 report_*.md
    round2_path = _pick_latest("combined_report_*.md", reports_dir)
    if not round2_path:
        logger.warning("未找到 combined_report_*.md，将尝试使用 report_*.md 作为第二轮输入。")
        round2_path = _pick_latest("report_*.md", reports_dir)
    if not round2_path:
        logger.error("在 %s 下未找到 combined_report_*.md 或 report_*.md，无法构造第二轮输入。", reports_dir)
        return 1

    logger.info("使用第一轮输入: %s", round1_path)
    logger.info("使用第二轮输入: %s", round2_path)

    round1_text = round1_path.read_text(encoding="utf-8")
    round2_text = round2_path.read_text(encoding="utf-8")

    service = PortfolioDecisionService()
    result = service.synthesize_decision(
        portfolio_round1_text=round1_text,
        round2_report_text=round2_text,
    )
    if not result:
        logger.error("第三轮决策服务未返回结果，请检查 LLM 配置。")
        return 1

    print("\n" + "=" * 80)
    print("组合第三轮决策输出：")
    print("=" * 80 + "\n")
    print(result.raw_text)
    print("\n" + "=" * 80)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"round3_decision_{ts}.md"
    out_path.write_text(result.raw_text, encoding="utf-8")
    logger.info("第三轮决策报告已保存到: %s", out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

