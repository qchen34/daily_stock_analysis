# -*- coding: utf-8 -*-
"""
多风格分析师辩论模块 - 角色与仓位配置

本文件只负责定义元数据（分析师角色、仓位分档等），不直接调用 LLM。
后续的辩论逻辑会在 services.debate_service 中引用这里的配置。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict


class PositionBucket(Enum):
    """
    仓位分档（便于在 Prompt 中使用自然语言描述当前仓位）。

    - EMPTY: 0%
    - LIGHT: 0-30%
    - MEDIUM: 30-70%
    - HEAVY: 70-100%
    """

    EMPTY = "empty"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


def bucket_position(position_pct: float) -> PositionBucket:
    """
    根据精确仓位百分比划分仓位档位。

    Args:
        position_pct: 当前总仓位百分比（0-100 之间，允许略超范围，将会裁剪）

    Returns:
        PositionBucket: 仓位档位
    """
    if position_pct is None:
        return PositionBucket.EMPTY

    try:
        v = float(position_pct)
    except (TypeError, ValueError):
        return PositionBucket.EMPTY

    if v <= 0:
        return PositionBucket.EMPTY
    if v < 30:
        return PositionBucket.LIGHT
    if v < 70:
        return PositionBucket.MEDIUM
    return PositionBucket.HEAVY


@dataclass(frozen=True)
class AnalystProfile:
    """
    虚拟分析师角色配置。

    这些角色会在 Prompt 中以“多角色辩论”的形式出现，每个角色有不同的关注点与风格。
    """

    id: str  # 程序内部使用的唯一 ID
    name: str  # 对外展示的称呼（例如 “防守型分析师A”）
    style_tagline: str  # 一句话风格描述
    description: str  # 更详细的人设（会拼入 Prompt）
    focus_areas: List[str]  # 该分析师重点关注的维度（趋势/估值/基本面/消息面等）

    def to_prompt_block(self) -> str:
        """
        将分析师配置转换为 Prompt 中的一小段角色说明。

        返回的文本会直接放进 system / user prompt 中，用于指导 LLM 模拟该角色的说话方式。
        """
        focus = ", ".join(self.focus_areas) if self.focus_areas else "综合视角"
        return (
            f"分析师ID: {self.id}\n"
            f"姓名/称呼: {self.name}\n"
            f"风格简介: {self.style_tagline}\n"
            f"详细人设: {self.description}\n"
            f"关注重点: {focus}\n"
        )


def get_default_analyst_profiles() -> List[AnalystProfile]:
    """
    返回系统内置的几位虚拟分析师角色。

    后续如果你想调优风格，只需修改这里的配置即可。
    """
    return [
        AnalystProfile(
            id="defensive",
            name="防守型分析师",
            style_tagline="极度重视回撤控制与资金安全，更倾向于避免大幅回撤。",
            description=(
                "偏好低回撤、稳健收益路径。看到风险时会优先考虑减仓或观望，"
                "只有当趋势、估值、风险事件都较为安全时，才会建议加仓。"
                "对高位放量、大幅乖离和坏消息非常敏感。"
            ),
            focus_areas=["风险控制", "仓位管理", "资金曲线稳定性"],
        ),
        AnalystProfile(
            id="aggressive",
            name="进攻型分析师",
            style_tagline="偏好趋势跟随与成长空间，能接受更大波动追求收益。",
            description=(
                "更关注中长期成长空间与趋势延续，只要风险可控且趋势尚在，"
                "即便短期波动较大，也愿意在关键支撑位积极建仓或加仓。"
                "对强势股、龙头股有更高容忍度。"
            ),
            focus_areas=["成长空间", "趋势延续性", "交易性机会"],
        ),
        AnalystProfile(
            id="technical",
            name="技术派分析师",
            style_tagline="严格依据技术形态与指标信号给出操作建议。",
            description=(
                "主要依赖技术指标与价格行为，包括均线系统、成交量、MACD、"
                "支撑位和压力位等。会给出相对精确的买入区间、止损位和止盈位，"
                "对形态破坏和指标背离非常敏感。"
            ),
            focus_areas=["趋势结构", "支撑压力", "量价配合", "MACD/KDJ"],
        ),
        AnalystProfile(
            id="fundamental",
            name="基本面分析师",
            style_tagline="从盈利质量与估值出发，关注中长期风险收益比。",
            description=(
                "优先评估公司基本面、行业景气度与估值水平。"
                "即便短期技术形态良好，如果估值明显偏贵或基本面存在隐患，"
                "也会保持谨慎或建议降低仓位。"
            ),
            focus_areas=["盈利与现金流", "估值合理性", "行业景气", "中长期逻辑"],
        ),
    ]


def get_analyst_profile_map() -> Dict[str, AnalystProfile]:
    """
    返回以 id 为 key 的分析师映射，便于后续按 ID 访问。
    """
    profiles = get_default_analyst_profiles()
    return {p.id: p for p in profiles}

