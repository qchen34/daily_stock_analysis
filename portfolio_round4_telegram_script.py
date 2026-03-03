# -*- coding: utf-8 -*-
"""
组合第四轮：基于第三轮决策输出，生成最终结构化报告并发送到 Telegram。

用法（在 daily_stock_analysis 目录下）：
    # 建议顺序：
    python main.py                          # 生成第二轮报告 + 设置 REPORTS_RUN_DIR
    python portfolio_round1_test_script.py  # 第一轮：组合分析
    python portfolio_round3_test_script.py  # 第三轮：综合决策
    python portfolio_round4_telegram_script.py  # 第四轮：结构化终稿 + Telegram 推送

逻辑：
1. 确定本次使用的 reports 目录（与前几轮保持一致）：
   - 优先 REPORTS_RUN_DIR
   - 否则 ./reports 下最新的时间戳子目录或根目录
2. 读取最新的 round3_decision_*.md 作为第三轮输入
3. 调用 PortfolioDecisionDebateService（第四轮）对第三轮决策进行「多分析师审阅与校准」
4. 将最终结构化报告保存为 round4_final_*.md
5. 通过 NotificationService 仅发送到 Telegram
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.notification import NotificationService
from src.services.portfolio_debate_service import PortfolioDebateService


logger = logging.getLogger(__name__)


def _pick_latest(pattern: str, directory: Path) -> Optional[Path]:
    candidates = list(directory.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _resolve_reports_dir(cwd: Path) -> Path:
    env_dir = os.getenv("REPORTS_RUN_DIR")
    if env_dir:
        d = Path(env_dir)
        logger.info("使用 REPORTS_RUN_DIR 指定的目录: %s", d)
        return d

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

    # 第一轮：组合分析输出
    round1_path = _pick_latest("portfolio_round1_*.md", reports_dir)
    if not round1_path:
        logger.error("在 %s 下未找到 portfolio_round1_*.md，请先运行第一轮脚本。", reports_dir)
        return 1

    # 第二轮：优先使用 round2_combined_*.md，其次 combined_report_*.md / report_*.md
    round2_path = _pick_latest("round2_combined_*.md", reports_dir)
    if not round2_path:
        round2_path = _pick_latest("combined_report_*.md", reports_dir)
    if not round2_path:
        logger.warning("未找到 round2_combined_*.md / combined_report_*.md，将尝试使用 report_*.md 作为第二轮输入。")
        round2_path = _pick_latest("report_*.md", reports_dir)
    if not round2_path:
        logger.error("在 %s 下未找到 combined_report_*.md 或 report_*.md，请先运行 main.py。", reports_dir)
        return 1

    # 第三轮：综合决策输出
    round3_path = _pick_latest("round3_decision_*.md", reports_dir)
    if not round3_path:
        logger.error("在 %s 下未找到 round3_decision_*.md，请先运行第三轮脚本。", reports_dir)
        return 1

    logger.info("使用第一轮输入: %s", round1_path)
    logger.info("使用第二轮输入: %s", round2_path)
    logger.info("使用第三轮输入: %s", round3_path)

    round1_text = round1_path.read_text(encoding="utf-8")
    round2_text = round2_path.read_text(encoding="utf-8")
    round3_text = round3_path.read_text(encoding="utf-8")

    # 第四轮：在前三轮基础上进行多分析师审阅与结构化输出
    debate_service = PortfolioDebateService()
    final_output = debate_service.debate_decision(
        round1_text=round1_text,
        round2_text=round2_text,
        round3_text=round3_text,
    )
    if not final_output:
        logger.error("第四轮辩论/定稿服务未返回结果，请检查 LLM 配置。")
        return 1

    print("\n" + "=" * 80)
    print("组合第四轮最终结构化报告：")
    print("=" * 80 + "\n")
    print(final_output.raw_text)
    print("\n" + "=" * 80)

    # 保存到同一 reports 目录
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"round4_final_{ts}.md"
    out_path.write_text(final_output.raw_text, encoding="utf-8")
    logger.info("第四轮最终报告已保存到: %s", out_path)

    # 通过 Telegram 发送（前 3 轮不发送）
    notifier = NotificationService()
    if not notifier.is_available():
        logger.warning("通知服务未配置可用渠道，跳过 Telegram 推送。")
        return 0

    if notifier.send_to_telegram(final_output.raw_text):
        logger.info("第四轮最终报告已发送到 Telegram。")
    else:
        logger.warning("第四轮最终报告发送到 Telegram 失败。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

