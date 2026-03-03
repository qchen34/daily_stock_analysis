# -*- coding: utf-8 -*-
"""
第一轮：个人组合（Portfolio）总体分析服务。

职责：
1. 从 PortfolioSnapshot（以及可选的 GuruHoldingsContext）构造组合视角的 Prompt
2. 调用 GeminiAnalyzer.run_custom_prompt 执行一次 LLM 分析
3. 返回原始文本输出，后续可以逐步收紧为结构化 JSON
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, List

from src.analyzer import GeminiAnalyzer
from src.core.position_profile import PortfolioSnapshot, HoldingPosition
from src.core.guru_profile import GuruHoldingsContext, GuruPortfolioSnapshot, GuruPosition


logger = logging.getLogger(__name__)


@dataclass
class PortfolioRound1Output:
    """
    第一轮输出的简单封装。

    目前只保留原始文本，方便你快速观察和调 Prompt；
    之后可以演进为 JSON 结构（例如 summary / risk / style_fit 等字段）。
    """

    raw_text: str


class PortfolioAnalysisService:
    """
    第一轮：基于个人组合的总体分析。
    """

    def __init__(self, analyzer: Optional[GeminiAnalyzer] = None):
        self._analyzer = analyzer or GeminiAnalyzer()

    def analyze_portfolio(
        self,
        portfolio: PortfolioSnapshot,
        *,
        guru_context: Optional[GuruHoldingsContext] = None,
    ) -> Optional[PortfolioRound1Output]:
        """
        对当前组合做一轮总体分析总结。

        - 输入：PortfolioSnapshot（必须），可选 GuruHoldingsContext
        - 输出：目前为一段 Markdown/纯文本，后续可以改为结构化 JSON
        """
        if not self._analyzer.is_available():
            logger.warning("LLM 分析器不可用，跳过组合第一轮分析")
            return None

        prompt = self._build_prompt(portfolio=portfolio, guru_context=guru_context)

        raw_text = self._analyzer.run_custom_prompt(
            prompt,
            max_output_tokens=2048,
            log_prefix="[组合第一轮分析]",
        )

        if not raw_text:
            return None

        return PortfolioRound1Output(raw_text=raw_text)

    def _build_prompt(
        self,
        *,
        portfolio: PortfolioSnapshot,
        guru_context: Optional[GuruHoldingsContext] = None,
    ) -> str:
        """
        构造第一轮组合分析的 Prompt。
        """
        lines: List[str] = []

        account = portfolio.account_name or "未命名账户"
        lines.append("你是一名专业的资产配置与风险管理顾问。")
        lines.append("请阅读下面这位投资者的当前股票组合，并给出结构化的中文分析总结。")
        lines.append("")
        lines.append("分析时请重点关注：整体仓位水平、集中度、风格暴露、风险点与改进方向。")
        lines.append("")

        # 组合基本信息
        lines.append("## 账户与整体信息")
        lines.append(f"- 账户名称：{account}")
        if portfolio.total_equity is not None:
            lines.append(f"- 披露的总资产（可能为静态配置）：约 {portfolio.total_equity:.2f}")
        lines.append("")

        # 组合持仓列表（只展示我们当前知道的静态信息）
        lines.append("## 当前持仓列表（来自配置）")
        if not portfolio.positions:
            lines.append("- 当前未持有任何标的。")
        else:
            for code, pos in portfolio.positions.items():
                name = pos.name or code
                cost = f"{pos.cost_price:.2f}" if pos.cost_price is not None else "未知"
                shares = f"{pos.shares:.2f}" if getattr(pos, "shares", None) is not None else "未知"
                static_pct = f"{pos.position_pct:.1f}%" if pos.position_pct else "未配置"
                note = pos.notes or ""
                lines.append(
                    f"- {name} ({code}) | 股数：{shares} | 成本价：{cost} | 静态仓位配置：{static_pct} | 备注：{note}"
                )
        lines.append("")

        # 可选：大佬组合的整体印象（这里只做简单罗列，不做详细指示）
        if guru_context and guru_context.portfolios:
            lines.append("## 大佬组合快照（用于风格参考）")
            for snap in guru_context.portfolios:
                assert isinstance(snap, GuruPortfolioSnapshot)
                lines.append(f"- 大佬：{snap.guru_name} | 风格：{snap.style_tagline or '未注明'}")
                if not snap.positions:
                    continue
                top_codes = list(snap.positions.keys())[:5]
                brief_list = []
                for c in top_codes:
                    p: GuruPosition = snap.positions[c]
                    brief_list.append(f"{p.name or c}({c}) 权重约 {p.weight_pct:.1f}%")
                if brief_list:
                    lines.append(f"  - 代表性持仓：{'; '.join(brief_list)}")
            lines.append("")

        # 输出格式要求
        lines.append("## 输出要求")
        lines.append("请用中文输出一段结构化分析，包含以下部分：")
        lines.append("1. 组合整体概览：用 3-5 句话评价当前组合的整体风格、进攻/防守倾向。")
        lines.append("2. 仓位与集中度：简单评估整体仓位水平和个股/板块集中度（可以根据标的类型做合理推断）。")
        lines.append("3. 风险点：列出 3-5 个最需要关注的风险（如单一行业暴露、成长股占比过高等）。")
        lines.append("4. 优化建议：给出 3-5 条可以在未来 3-6 个月逐步优化组合的建议（不需要具体买卖点）。")
        lines.append("")
        lines.append("不需要输出 JSON，只需输出有清晰小标题的 Markdown 文本即可。")
        lines.append("")
        lines.append("## 免责声明")
        lines.append("本报告基于 AI 模型生成，可能存在理解偏差或事实错误，仅供学习与交流，不构成任何投资建议。实际投资决策请结合个人风险承受能力与专业意见谨慎判断。")

        return "\n".join(lines)

