"""Render an approved immutable snapshot without inventing verified evidence."""

from __future__ import annotations

from app.schemas.domain import CaseRevision, DebateCase, ReasoningNode


def _reasoning(node: ReasoningNode, depth: int) -> list[str]:
    label = f"{node.label} [{node.kind}]："
    lines = [f'{"  " * depth}- {label}{node.content}']
    for child in sorted(node.children, key=lambda item: item.order):
        lines.extend(_reasoning(child, depth + 1))
    return lines


def render_revision_markdown(revision: CaseRevision) -> str:
    return render_case_markdown(revision.snapshot)


def render_case_markdown(case: DebateCase) -> str:
    lines = [
        f"# {case.motion}",
        "",
        f"持方：{case.side}",
        f"核心主张：{case.thesis}",
        "",
        "## 定义与判准",
    ]
    lines.extend(f"- {key}：{value}" for key, value in case.definitions.items())
    lines.extend(f"- 判准：{criterion}" for criterion in case.judging_criteria)
    lines.extend(["", "## 论点"])
    for argument in sorted(case.arguments, key=lambda item: item.order):
        lines.extend([
            f"### {argument.order + 1}. {argument.title}", "",
            f"主张：{argument.core_claim}", f"解释：{argument.explanation}", "",
            "机理：",
        ])
        for node in sorted(argument.reasoning_nodes, key=lambda item: item.order):
            lines.extend(_reasoning(node, 0))
        lines.append(f"影响：{argument.impact}")
        for item in argument.attack_defense:
            lines.append(f"- 攻防：对方主张「{item.opposing_claim}」；回应「{item.response}」")
            lines.append(f"  比较：{item.weighing}")
        if argument.evidence_needs:
            lines.extend(["", "待查证据（非已核验事实）："])
            lines.extend(
                f"- 待查：{need.question}；建议来源：{need.acceptable_source}"
                for need in argument.evidence_needs
            )
        lines.append("")
    lines.extend(["## 比较与整体策略", case.weighing, case.overall_strategy, ""])
    return "\n".join(lines)
