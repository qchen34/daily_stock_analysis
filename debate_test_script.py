# -*- coding: utf-8 -*-
"""
多分析师辩论模块快速自测脚本

用法（在项目根目录）：
    pip install -r requirements.txt   # 确保依赖已装好
    python debate_test_script.py      # 默认从最近一次分析历史中取一条做辩论

可选环境变量：
    TEST_STOCK_CODE=600519            # 只针对某只股票最近一条分析记录做辩论
    TEST_DAYS=7                       # 在最近多少天内查找历史记录，默认 30
    TEST_LIMIT=20                     # 最多取多少条记录中选第一条，默认 20

脚本逻辑：
1. 通过 DatabaseManager / AnalysisRepository 取一条最近的 AnalysisHistory 记录
2. 从记录中的 raw_result（JSON）还原出 AnalysisResult（尽量填充已有字段）
3. 假定当前仓位为 0%（或者你可以手工改成任意数值），调用 DebateService.run_debate()
4. 将生成的辩论 Markdown 打印到终端，并可选保存到本地文件
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from src.config import get_config
from src.analyzer import AnalysisResult
from src.services.debate_service import DebateService
from src.core.position_profile import HoldingPosition, PortfolioSnapshot, get_position_pct_for_code
from src.core.guru_profile import GuruHoldingsContext, GuruPortfolioSnapshot, GuruPosition
from src.repositories.analysis_repo import AnalysisRepository
from src.storage import DatabaseManager, AnalysisHistory


logger = logging.getLogger(__name__)


def _build_analysis_result_from_history(row: AnalysisHistory) -> AnalysisResult:
    """
    尝试从 AnalysisHistory 行记录还原出一个尽量完整的 AnalysisResult。

    如果 row.raw_result 里有完整 JSON，就尽可能用它来填充字段；
    否则退化为仅使用基本字段（code/name/sentiment_score 等）。
    """
    base_kwargs: Dict[str, Any] = {
        "code": row.code,
        "name": row.name or f"股票{row.code}",
        "sentiment_score": row.sentiment_score or 50,
        "trend_prediction": row.trend_prediction or "震荡",
        "operation_advice": row.operation_advice or "持有",
    }

    # row.raw_result 可能是 JSON 字符串，里面包含 dashboard 等字段
    raw_data: Dict[str, Any] = {}
    if getattr(row, "raw_result", None):
        try:
            raw_data = json.loads(row.raw_result)
        except Exception:
            # 解析失败就忽略，走简化路径
            raw_data = {}

    def pick(name: str, default: Any = "") -> Any:
        return raw_data.get(name, getattr(row, name, default))

    # 尽量补齐常用字段
    base_kwargs.update(
        dict(
            dashboard=raw_data.get("dashboard"),
            trend_analysis=pick("trend_analysis", ""),
            short_term_outlook=pick("short_term_outlook", ""),
            medium_term_outlook=pick("medium_term_outlook", ""),
            technical_analysis=pick("technical_analysis", ""),
            ma_analysis=pick("ma_analysis", ""),
            volume_analysis=pick("volume_analysis", ""),
            pattern_analysis=pick("pattern_analysis", ""),
            fundamental_analysis=pick("fundamental_analysis", ""),
            sector_position=pick("sector_position", ""),
            company_highlights=pick("company_highlights", ""),
            news_summary=pick("news_summary", row.news_content or ""),
            market_sentiment=pick("market_sentiment", ""),
            hot_topics=pick("hot_topics", ""),
            analysis_summary=pick("analysis_summary", row.analysis_summary or ""),
            key_points=pick("key_points", ""),
            risk_warning=pick("risk_warning", ""),
            buy_reason=pick("buy_reason", ""),
        )
    )

    return AnalysisResult(**base_kwargs)


def pick_latest_history(
    repo: AnalysisRepository,
    code: Optional[str] = None,
    days: int = 30,
    limit: int = 20,
) -> Optional[AnalysisHistory]:
    """
    从历史记录中选出一条最近的用来做辩论测试。
    """
    records = repo.get_list(code=code, days=days, limit=limit)
    if not records:
        logger.warning("在最近 %d 天内未找到任何分析历史记录（code=%s）", days, code or "ALL")
        return None

    # AnalysisRepository.get_list 默认已经按时间倒序返回（依赖底层实现），这里再保险按 created_at 排序一次
    records_sorted = sorted(
        records,
        key=lambda r: r.created_at or datetime.min,
        reverse=True,
    )
    return records_sorted[0]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    config = get_config()
    logger.info("使用数据库路径: %s", config.database_path)

    # 初始化数据库单例，确保表结构已准备好
    DatabaseManager.get_instance()

    repo = AnalysisRepository()

    test_code = os.getenv("TEST_STOCK_CODE") or None
    test_days = int(os.getenv("TEST_DAYS", "30"))
    test_limit = int(os.getenv("TEST_LIMIT", "20"))

    row = pick_latest_history(repo, code=test_code, days=test_days, limit=test_limit)
    if row is None:
        logger.error("没有可用于辩论测试的历史记录，先跑一次正常分析再试。")
        return 1

    logger.info(
        "选中历史记录: code=%s name=%s created_at=%s query_id=%s",
        row.code,
        row.name,
        getattr(row, "created_at", None),
        getattr(row, "query_id", None),
    )

    base_result = _build_analysis_result_from_history(row)

    # 从 user_portfolio.json 读取个人组合，推导当前标的仓位
    portfolio: Optional[PortfolioSnapshot] = None
    try:
        portfolio_path = os.path.join(os.getcwd(), "user_portfolio.json")
        if os.path.exists(portfolio_path):
            logger.info("从 %s 读取用户组合信息用于辩论...", portfolio_path)
            with open(portfolio_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            positions_dict: Dict[str, HoldingPosition] = {}
            for p in raw.get("positions", []):
                code = p.get("code")
                if not code:
                    continue
                positions_dict[code] = HoldingPosition(
                    code=code,
                    name=p.get("name"),
                    position_pct=p.get("position_pct", 0.0),
                    cost_price=p.get("cost_price"),
                    notes=p.get("notes"),
                )
            portfolio = PortfolioSnapshot(
                positions=positions_dict,
                total_equity=raw.get("total_equity"),
                as_of=raw.get("as_of"),
                account_name=raw.get("account_name"),
            )
        else:
            logger.warning("未找到 user_portfolio.json，将使用 0%% 仓位作为默认值。")
    except Exception as e:
        logger.error("读取 user_portfolio.json 失败，将使用 0%% 仓位: %s", e)
        portfolio = None

    position_pct = get_position_pct_for_code(portfolio, base_result.code)
    logger.info("根据用户组合推导的当前仓位: %.1f%%", position_pct)

    # 可选：从 guru_holdings.json 构造大佬持仓上下文
    guru_context: Optional[GuruHoldingsContext] = None
    try:
        guru_path = os.path.join(os.getcwd(), "guru_holdings.json")
        if os.path.exists(guru_path):
            logger.info("从 %s 读取大佬持仓信息用于辩论...", guru_path)
            with open(guru_path, "r", encoding="utf-8") as f:
                raw_g = json.load(f)
            portfolios: List[GuruPortfolioSnapshot] = []
            for snap in raw_g.get("portfolios", []):
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
            if portfolios:
                guru_context = GuruHoldingsContext(portfolios=portfolios)
        else:
            logger.warning("未找到 guru_holdings.json，将跳过大佬持仓上下文。")
    except Exception as e:
        logger.error("读取 guru_holdings.json 失败，将忽略大佬持仓上下文: %s", e)
        guru_context = None

    debate_service = DebateService()
    debate = debate_service.run_debate(
        base_result,
        position_pct=position_pct,
        guru_context=guru_context,
    )

    if not debate:
        logger.error("辩论模块返回为空，请检查 LLM 配置（Gemini/Anthropic/OpenAI）是否可用。")
        return 1

    markdown = debate.to_markdown()

    print("\n" + "=" * 80)
    print("多风格分析师辩论 Markdown 输出：")
    print("=" * 80 + "\n")
    print(markdown)
    print("\n" + "=" * 80)

    # 可选：保存到本地文件，便于和原报告一起打开查看
    out_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"debate_{row.code}_{ts}.md"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info("辩论结果已保存到: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

