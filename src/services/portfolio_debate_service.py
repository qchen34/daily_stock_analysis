# -*- coding: utf-8 -*-
"""
第四轮：对第三轮组合决策进行多分析师审阅与定稿的服务。

职责：
1. 接收第三轮决策文本（round3_decision_*.md）
2. 以多风格分析师委员会的方式审阅已有决策，补充遗漏的风险点和执行细节
3. 输出一份结构化、适合直接发送给终端用户（Telegram）的最终报告（Markdown）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.analyzer import GeminiAnalyzer


logger = logging.getLogger(__name__)


@dataclass
class PortfolioRound4Output:
    """
    第四轮输出：最终要发给用户看的组合操作报告。
    """

    raw_text: str


class PortfolioDebateService:
    """
    第四轮：多分析师审阅与定稿服务。
    """

    def __init__(self, analyzer: Optional[GeminiAnalyzer] = None):
        self._analyzer = analyzer or GeminiAnalyzer()

    def debate_decision(
        self,
        *,
        round1_text: str,
        round2_text: str,
        round3_text: str,
    ) -> Optional[PortfolioRound4Output]:
        """
        基于前三轮的组合分析结果，输出一份更结构化、可直接执行的终稿。

        Args:
            round1_text: 第一轮组合分析输出（个人持仓视角）
            round2_text: 第二轮大盘+个股报告（技术面/基本面/情绪面）
            round3_text: 第三轮综合决策草稿（风险+仓位管理建议）
        """
        if not self._analyzer.is_available():
            logger.warning("LLM 分析器不可用，跳过第四轮辩论/定稿。")
            return None

        prompt = self._build_prompt(
            round1_text=round1_text,
            round2_text=round2_text,
            round3_text=round3_text,
        )

        raw_text = self._analyzer.run_custom_prompt(
            prompt,
            max_output_tokens=2048,
            log_prefix="[组合第四轮终稿]",
        )
        if not raw_text:
            return None

        return PortfolioRound4Output(raw_text=raw_text)

    def _build_prompt(
        self,
        *,
        round1_text: str,
        round2_text: str,
        round3_text: str,
    ) -> str:
        """
        构造第四轮终稿 Prompt，强调结构化输出与执行友好。
        """
        lines = []

        lines.append("你现在是一个由多位风格各异的投资顾问组成的“投资委员会”。")
        lines.append("你们已经拿到了一套完整的四轮分析材料，请在此基础上进行审阅、补充和结构化整理，产出一份可以直接发给终端用户的“今日组合执行指南”。")
        lines.append("")
        lines.append("下面依次给出前三轮的分析结果：")
        lines.append("")
        lines.append("【第一轮：个人组合与仓位分析（Portfolio 视角）】")
        lines.append(round1_text.strip())
        lines.append("")
        lines.append("【第二轮：大盘与个股详细分析（技术面/基本面/情绪面）】")
        lines.append(round2_text.strip())
        lines.append("")
        lines.append("【第三轮：综合风险与仓位管理决策草稿】")
        lines.append(round3_text.strip())
        lines.append("")

        lines.append("## 输出要求（请严格按照以下结构输出 Markdown）")
        lines.append("")
        lines.append("使用如下一级/二级标题结构，不要添加额外的顶层标题：")
        lines.append("")
        lines.append("### 一、今日组合执行总览")
        lines.append("- 用 3-6 句话总结今天整体应该采取的态度（进攻/观望/防守）、大致仓位区间以及主要逻辑；")
        lines.append("- 明确指出该判断与第一轮“个人组合分析”和第三轮“风险/仓位决策草稿”的对应关系。")
        lines.append("")
        lines.append("### 二、个人持仓与大佬持仓概览")
        lines.append("- 用小节分别总结：")
        lines.append("  - 个人组合与当前仓位结构：从第一轮材料中抽取关键信息（总仓位、现金、风格暴露、集中度等）；")
        lines.append("  - 关键大佬持仓与风格：从第二轮/相关材料中抽取对你影响最大的大佬组合及其代表性持仓；")
        lines.append("- 简要说明当前计划在多大程度上顺应或逆向这些大佬的行为（例如“部分跟随”“保持独立”）。")
        lines.append("")
        lines.append("### 三、组合层面仓位与风险控制")
        lines.append("- 目标总仓位区间（例如 30%-50% / 60%-80%）及现金比例建议；")
        lines.append("- 仓位变化的原则（在什么情况下逐步加仓/减仓）；")
        lines.append("- 对单一行业/单一标的集中度的提醒。")
        lines.append("")
        lines.append("### 四、重点标的操作清单")
        lines.append("以列表形式列出重点标的（只包含当前持仓或前三轮中反复提及的标的），每个标的包含：")
        lines.append("- 标的名称（代码）；")
        lines.append("- 今日建议动作：减仓 / 观望 / 小幅加仓 / 积极加仓；")
        lines.append("- 建议的目标仓位区间（如果适用）；")
        lines.append("- 1-2 句简短理由（可以引用估值/技术形态/筹码/情绪/大佬行为中的关键点）。")
        lines.append("")
        lines.append("### 五、风险提示清单")
        lines.append("- 列出 3-6 条当下最重要的风险因素，每条一行，语言简洁具体；")
        lines.append("- 包括但不限于：宏观不确定性、政策风险、行业景气度、单一标的波动性等。")
        lines.append("")
        lines.append("### 六、执行节奏与复盘提醒")
        lines.append("- 给出未来 3-5 个交易日的执行节奏建议（例如分几次调整、每次的触发条件是价格/波动幅度/事件等）；")
        lines.append("- 提醒用户在什么时间点或条件下需要重新评估当前计划（例如“若某标的大幅突破/跌破某区间则需要重新开会”）。")
        lines.append("")
        lines.append("注意事项：")
        lines.append("- 不要输出 JSON，仅输出 Markdown 文本；")
        lines.append("- 不要生成过长的段落，尽量使用列表，提高可读性；")
        lines.append("- 不必显式展现“内部辩论过程”，只需给出委员会达成的一致终稿。")
        lines.append("")
        lines.append("## 免责声明")
        lines.append("本报告基于 AI 模型生成，可能存在理解偏差或事实错误，仅供学习与交流，不构成任何投资建议。实际投资决策请结合个人风险承受能力与专业意见谨慎判断。")

        return "\n".join(lines)

