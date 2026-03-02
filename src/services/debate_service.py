# -*- coding: utf-8 -*-
"""
多风格分析师辩论服务层

职责：
1. 基于已有的单股分析结果（AnalysisResult）和持仓信息，构造多角色辩论 Prompt
2. 调用通用 LLM 客户端（GeminiAnalyzer.run_custom_prompt）完成一次多分析师辩论
3. 解析模型返回的 JSON 结果，生成结构化的 DebateResult
4. 提供 to_markdown()，输出可直接拼接到个股报告末尾的 Markdown 段落
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from json_repair import repair_json

from src.analyzer import AnalysisResult, GeminiAnalyzer
from src.core.debate_profile import AnalystProfile, PositionBucket, get_default_analyst_profiles
from src.core.position_profile import describe_position_bucket


logger = logging.getLogger(__name__)


@dataclass
class DebateAnalystView:
    """
    单个虚拟分析师在本次辩论中的观点摘要。
    """

    id: str
    name: str
    stance: str
    summary: str
    arguments: List[str] = field(default_factory=list)
    advice_for_current_position: str = ""
    comment_on_others: Dict[str, str] = field(default_factory=dict)


@dataclass
class DebateResult:
    """
    多分析师辩论的结构化结果。
    """

    stock_code: str
    stock_name: str
    position_pct: float
    position_bucket: PositionBucket
    position_description: str

    analysts: List[DebateAnalystView] = field(default_factory=list)
    consensus_summary: str = ""
    consensus_action_no_position: str = ""
    consensus_action_has_position: str = ""
    consensus_risks: List[str] = field(default_factory=list)
    consensus_opportunities: List[str] = field(default_factory=list)

    raw_json: Dict[str, Any] = field(default_factory=dict)
    raw_text: Optional[str] = None

    def to_markdown(self) -> str:
        """
        转换为 Markdown 段落，可直接插入到个股报告末尾。
        """
        lines: List[str] = []

        lines.append("## 多风格分析师辩论")
        lines.append("")
        lines.append(f"- 标的：**{self.stock_name} ({self.stock_code})**")
        lines.append(f"- 当前仓位：{self.position_description}")
        lines.append("")

        if not self.analysts and not self.consensus_summary and self.raw_text:
            # 解析失败时的降级方案：直接附上原始辩论内容
            lines.append("以下为多位虚拟分析师围绕该标的的辩论纪要（原始内容）：")
            lines.append("")
            lines.append(self.raw_text)
            return "\n".join(lines)

        for view in self.analysts:
            stance = view.stance or "观点未明确"
            lines.append(f"### {view.name}（{stance}）")
            if view.summary:
                lines.append("")
                lines.append(view.summary)
            if view.arguments:
                lines.append("")
                lines.append("**核心观点要点：**")
                for arg in view.arguments:
                    lines.append(f"- {arg}")
            if view.advice_for_current_position:
                lines.append("")
                lines.append(f"**结合当前仓位的操作建议：**{view.advice_for_current_position}")
            if view.comment_on_others:
                lines.append("")
                lines.append("**对其他分析师观点的简要点评：**")
                for target_id, comment in view.comment_on_others.items():
                    # target_id 可以是角色 ID 或角色名称，这里不强行格式化
                    lines.append(f"- 针对 {target_id}：{comment}")
            lines.append("")

        if (
            self.consensus_summary
            or self.consensus_action_no_position
            or self.consensus_action_has_position
            or self.consensus_risks
            or self.consensus_opportunities
        ):
            lines.append("### 🧩 综合结论")
            if self.consensus_summary:
                lines.append("")
                lines.append(self.consensus_summary)

            if self.consensus_action_no_position or self.consensus_action_has_position:
                lines.append("")
                lines.append("**按持仓类型的行动建议：**")
                if self.consensus_action_no_position:
                    lines.append(f"- 空仓者：{self.consensus_action_no_position}")
                if self.consensus_action_has_position:
                    lines.append(f"- 持仓者：{self.consensus_action_has_position}")

            if self.consensus_risks:
                lines.append("")
                lines.append("**需要重点关注的风险点：**")
                for r in self.consensus_risks:
                    lines.append(f"- {r}")

            if self.consensus_opportunities:
                lines.append("")
                lines.append("**潜在机会与催化：**")
                for o in self.consensus_opportunities:
                    lines.append(f"- {o}")

        return "\n".join(lines)


class DebateService:
    """
    多风格分析师辩论服务。

    使用方式：
        service = DebateService()
        debate = service.run_debate(base_result, position_pct=35.0)
        markdown = debate.to_markdown()
    """

    def __init__(self, analyzer: Optional[GeminiAnalyzer] = None):
        self._analyzer = analyzer or GeminiAnalyzer()

    def run_debate(
        self,
        base_result: AnalysisResult,
        position_pct: Optional[float] = None,
        analyst_profiles: Optional[List[AnalystProfile]] = None,
    ) -> Optional[DebateResult]:
        """
        执行一次多分析师辩论。

        Args:
            base_result: 单股分析的基础结果（主分析）
            position_pct: 当前标的在组合中的仓位百分比（0-100），None 视为 0
            analyst_profiles: 可选的分析师人设列表，默认使用内置配置
        """
        if not self._analyzer.is_available():
            logger.warning("LLM 分析器不可用，跳过辩论模块")
            return None

        stock_code = base_result.code
        stock_name = base_result.name or f"股票{stock_code}"

        try:
            pos_value = float(position_pct) if position_pct is not None else 0.0
        except (TypeError, ValueError):
            pos_value = 0.0

        bucket, desc = describe_position_bucket(pos_value)

        profiles = analyst_profiles or get_default_analyst_profiles()
        prompt = self._build_prompt(
            base_result=base_result,
            position_pct=pos_value,
            position_bucket=bucket,
            position_desc=desc,
            analyst_profiles=profiles,
        )

        raw_text = self._analyzer.run_custom_prompt(
            prompt,
            max_output_tokens=4096,
            log_prefix="[多分析师辩论]",
        )

        debate_result = self._parse_response(
            raw_text=raw_text,
            stock_code=stock_code,
            stock_name=stock_name,
            position_pct=pos_value,
            position_bucket=bucket,
            position_desc=desc,
            profiles=profiles,
        )
        return debate_result

    def _build_prompt(
        self,
        base_result: AnalysisResult,
        position_pct: float,
        position_bucket: PositionBucket,
        position_desc: str,
        analyst_profiles: List[AnalystProfile],
    ) -> str:
        """
        构造用于多分析师辩论的 Prompt。
        """
        stock_code = base_result.code
        stock_name = base_result.name or f"股票{stock_code}"

        # 主分析摘要（给辩论者作为“背景材料”）
        sniper_points = {}
        try:
            sniper_points = base_result.get_sniper_points() or {}
        except Exception:
            sniper_points = {}

        core_conclusion = base_result.get_core_conclusion()

        lines: List[str] = []
        lines.append("你现在是一组虚拟投资委员会，包含多位风格各异的分析师，将围绕同一只股票进行辩论。")
        lines.append("请在充分尊重“主分析结果”和“当前持仓信息”的前提下，给出更立体、带有分歧的决策建议。")
        lines.append("")
        lines.append("## 标的与持仓信息")
        lines.append(f"- 股票代码：{stock_code}")
        lines.append(f"- 股票名称：{stock_name}")
        lines.append(f"- 当前仓位：{position_desc}（约 {position_pct:.1f}%）")
        lines.append("")
        lines.append("## 主分析结果（基础共识）")
        lines.append(f"- 总体情绪评分：{base_result.sentiment_score}")
        lines.append(f"- 趋势判断：{base_result.trend_prediction}")
        lines.append(f"- 操作建议：{base_result.operation_advice}")
        if core_conclusion:
            lines.append(f"- 核心结论：{core_conclusion}")
        if base_result.risk_warning:
            lines.append("")
            lines.append("### 关键风险提示（来自主分析）")
            lines.append(base_result.risk_warning)
        if base_result.news_summary:
            lines.append("")
            lines.append("### 新闻与舆情摘要（来自主分析）")
            lines.append(base_result.news_summary)
        if sniper_points:
            lines.append("")
            lines.append("### 参考操作点位（来自主分析，供讨论时参考，不必盲从）")
            for k, v in sniper_points.items():
                lines.append(f"- {k}: {v}")

        # 分析师人设
        lines.append("")
        lines.append("## 虚拟分析师人设（请严格按照这些角色来发言）")
        for prof in analyst_profiles:
            lines.append("")
            lines.append(prof.to_prompt_block())

        # 具体任务与输出格式
        lines.append("")
        lines.append("## 辩论任务")
        lines.append("1. 每位分析师先给出自己基于当前持仓的独立观点，回答：应当加仓 / 减仓 / 观望 / 止损 / 逐步撤退 等。")
        lines.append("2. 在观点中，必须明确：")
        lines.append("   - 自己关注的核心维度（风险 / 估值 / 趋势 / 基本面 / 消息面等）")
        lines.append("   - 对当前仓位是否合理的评价（过轻 / 合理 / 过重）")
        lines.append("   - 针对当前仓位的具体操作建议（例如：加到几成仓、分几次、触发条件是什么）。")
        lines.append("3. 然后每位分析师需要简要评论至少 1 位其他分析师的观点：指出你同意和不同意的点。")
        lines.append("4. 最后由你综合所有角色的观点，形成一个“综合结论”，给出对空仓者 vs 持仓者的差异化建议。")

        lines.append("")
        lines.append("## 输出格式（必须是合法 JSON，不要包含多余文本）")
        lines.append("请严格输出一个 JSON 对象，结构如下：")
        lines.append("""```json
{
  "stock_code": "代码",
  "stock_name": "名称",
  "position_pct": 35.0,
  "position_bucket": "LIGHT/MEDIUM/HEAVY/EMPTY",
  "position_comment": "用自然语言描述当前仓位是否合理",
  "analysts": [
    {
      "id": "defensive",
      "name": "防守型分析师",
      "stance": "看多/看空/观望/中性",
      "summary": "一句话概括该分析师的总体态度和结论",
      "arguments": [
        "要点1",
        "要点2"
      ],
      "advice_for_current_position": "结合当前仓位，给出具体操作建议（如：分两次减到轻仓，跌破某价位必须止损）",
      "comment_on_others": {
        "aggressive": "对进攻型分析师观点的简要评价",
        "technical": "对技术派分析师观点的简要评价"
      }
    }
  ],
  "consensus": {
    "summary": "综合所有角色后，对该标的的总体结论（可以保留分歧，但要说明主导观点）",
    "action_advice": {
      "no_position": "针对完全空仓者的建议（是否可以建仓，建多少，节奏如何）",
      "has_position": "针对已有持仓者的建议（是加仓、减仓还是耐心持有，以及大致仓位区间）"
    },
    "risk_points": [
      "需要重点关注的风险1",
      "需要重点关注的风险2"
    ],
    "opportunity_points": [
      "可能的机会或催化1",
      "可能的机会或催化2"
    ]
  }
}
```""")

        lines.append("")
        lines.append("请只输出上述 JSON，不要添加任何自然语言解释或 Markdown 标题。")

        return "\n".join(lines)

    def _parse_response(
        self,
        raw_text: str,
        stock_code: str,
        stock_name: str,
        position_pct: float,
        position_bucket: PositionBucket,
        position_desc: str,
        profiles: List[AnalystProfile],
    ) -> DebateResult:
        """
        解析 LLM 返回的 JSON，构造 DebateResult。
        """
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # 去掉可能的 markdown 代码块包裹
            cleaned = cleaned.strip("`")
            # 简单兜底：如果仍然包含 ```json 标记，再做一次替换
        if "```json" in cleaned or "```" in cleaned:
            cleaned = cleaned.replace("```json", "").replace("```", "")

        # 尝试修复并解析 JSON
        data: Dict[str, Any] = {}
        try:
            repaired = repair_json(cleaned)
            data = json.loads(repaired)
        except Exception as e:
            logger.warning("解析辩论 JSON 失败，将以原始文本形式返回: %s", e)
            return DebateResult(
                stock_code=stock_code,
                stock_name=stock_name,
                position_pct=position_pct,
                position_bucket=position_bucket,
                position_description=position_desc,
                raw_text=raw_text,
            )

        # 解析分析师观点
        analyst_map = {p.id: p for p in profiles}
        analyst_views: List[DebateAnalystView] = []
        for item in data.get("analysts", []) or []:
            try:
                a_id = str(item.get("id") or "").strip() or "unknown"
                profile = analyst_map.get(a_id)
                name = item.get("name") or (profile.name if profile else a_id)
                stance = item.get("stance") or ""
                summary = item.get("summary") or ""
                arguments = item.get("arguments") or []
                if not isinstance(arguments, list):
                    arguments = [str(arguments)]
                comment_on_others = item.get("comment_on_others") or {}
                if not isinstance(comment_on_others, dict):
                    comment_on_others = {}

                view = DebateAnalystView(
                    id=a_id,
                    name=str(name),
                    stance=str(stance),
                    summary=str(summary),
                    arguments=[str(x) for x in arguments],
                    advice_for_current_position=str(item.get("advice_for_current_position") or ""),
                    comment_on_others={str(k): str(v) for k, v in comment_on_others.items()},
                )
                analyst_views.append(view)
            except Exception as e:
                logger.debug("解析单个分析师观点失败，已跳过: %s", e)
                continue

        consensus = data.get("consensus") or {}
        action_advice = consensus.get("action_advice") or {}
        risk_points = consensus.get("risk_points") or []
        opportunity_points = consensus.get("opportunity_points") or []
        if not isinstance(risk_points, list):
            risk_points = [str(risk_points)]
        if not isinstance(opportunity_points, list):
            opportunity_points = [str(opportunity_points)]

        return DebateResult(
            stock_code=data.get("stock_code", stock_code),
            stock_name=data.get("stock_name", stock_name),
            position_pct=float(data.get("position_pct", position_pct) or 0.0),
            position_bucket=position_bucket,
            position_description=data.get("position_comment", position_desc) or position_desc,
            analysts=analyst_views,
            consensus_summary=consensus.get("summary") or "",
            consensus_action_no_position=action_advice.get("no_position") or "",
            consensus_action_has_position=action_advice.get("has_position") or "",
            consensus_risks=[str(x) for x in risk_points],
            consensus_opportunities=[str(x) for x in opportunity_points],
            raw_json=data,
            raw_text=raw_text,
        )

