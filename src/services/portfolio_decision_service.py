# -*- coding: utf-8 -*-
"""
第三轮：基于前两轮输出和风险/仓位管理的最终操作建议服务。

职责：
1. 接收第一轮组合分析摘要（文本）和第二轮个股/大盘报告（文本）
2. 基于风险管理、仓位管理、个人风格与大佬参考，生成「今天应该如何操作」的综合建议
3. 返回原始 Markdown 文本，方便人工审阅和后续结构化
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.analyzer import GeminiAnalyzer


logger = logging.getLogger(__name__)


@dataclass
class PortfolioRound3Output:
    """
    第三轮输出：当前不做强结构化，仅封装原始文本。
    后续可以根据需要演进为 JSON（目标仓位、加减仓节奏等字段）。
    """

    raw_text: str


class PortfolioDecisionService:
    """
    第三轮：结合前两轮输出给出最终操作建议。
    """

    def __init__(self, analyzer: Optional[GeminiAnalyzer] = None):
        self._analyzer = analyzer or GeminiAnalyzer()

    def synthesize_decision(
        self,
        *,
        portfolio_round1_text: str,
        round2_report_text: str,
    ) -> Optional[PortfolioRound3Output]:
        """
        生成最终操作建议。

        Args:
            portfolio_round1_text: 第一轮组合分析的文本输出
            round2_report_text: 第二轮个股/大盘报告的文本输出
        """
        if not self._analyzer.is_available():
            logger.warning("LLM 分析器不可用，跳过第三轮决策分析")
            return None

        prompt = self._build_prompt(
            portfolio_round1_text=portfolio_round1_text,
            round2_report_text=round2_report_text,
        )

        raw_text = self._analyzer.run_custom_prompt(
            prompt,
            max_output_tokens=2048,
            log_prefix="[组合第三轮决策]",
        )
        if not raw_text:
            return None

        return PortfolioRound3Output(raw_text=raw_text)

    def _build_prompt(
        self,
        *,
        portfolio_round1_text: str,
        round2_report_text: str,
    ) -> str:
        """
        构造第三轮决策 Prompt。
        """
        lines = []

        lines.append("你是一名严格执行风险控制和仓位管理原则的投资顾问。")
        lines.append("下面给出两份已经生成的分析材料，请你在此基础上给出**今天应该如何操作**的综合建议。")
        lines.append("")
        lines.append("材料一：个人组合视角的第一轮分析摘要（供参考，不必逐句复述）：")
        lines.append("")
        lines.append(portfolio_round1_text.strip())
        lines.append("")
        lines.append("材料二：当前持仓相关个股的第二轮详尽分析与大盘/个股报告（供参考，不必逐句复述）：")
        lines.append("")
        lines.append(round2_report_text.strip())
        lines.append("")

        lines.append("## 输出目标")
        lines.append("在充分阅读上述两份材料后，请你以“风险与仓位管理”为核心，给出一份中文 Markdown 决策建议，包含：")
        lines.append("1. 组合层面的总体判断：今天整体应偏进攻、观望还是防守？理由是什么？")
        lines.append("2. 仓位管理建议：")
        lines.append("   - 给出一个建议的目标总仓位区间（例如 30%-50% / 60%-80% 等）；")
        lines.append("   - 如有必要，说明现金应保留的大致比例及原因。")
        lines.append("3. 重点标的操作建议（只覆盖当前持仓或报告中重点提及的标的）：")
        lines.append("   - 对每只标的，用列表形式给出：当前应以“减仓/观望/小幅加仓/积极加仓”等为主；")
        lines.append("   - 简短说明理由，尤其是与风险、估值、技术形态、筹码、情绪相关的因素。")
        lines.append("4. 风险提示：列出 3-5 条**今天不宜重仓或激进操作的原因**（如宏观不确定性、单一行业集中度过高等）。")
        lines.append("5. 执行节奏建议：给出未来 3-5 个交易日的大致执行节奏（例如“分三次加仓”“按回调幅度分批买入”等，不需要给出具体价格）。")
        lines.append("")
        lines.append("请注意：")
        lines.append("- 不要简单重复材料一和材料二的内容，而是要在其基础上做决策层的综合。")
        lines.append("- 不需要输出 JSON，直接用有层次的小标题和列表给出建议即可。")
        lines.append("")
        lines.append("## 免责声明")
        lines.append("本报告基于 AI 模型生成，可能存在理解偏差或事实错误，仅供学习与交流，不构成任何投资建议。实际投资决策请结合个人风险承受能力与专业意见谨慎判断。")

        return "\n".join(lines)

