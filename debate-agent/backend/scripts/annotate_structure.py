"""Build local, source-grounded structural annotations; never modify source manuscripts."""

import argparse
import hashlib
import json
import re
from pathlib import Path

NAMED = {
    "【正】如果ai能写出更好的情书我还要_不要自己写.md": "S-AI-LETTER",
    "【正】语言是_不是人类的边界.md": "S-LANGUAGE",
    "如果爱可以量化-框架.md": "S-LOVE-QUANTIFICATION",
}
ROLE_HINTS = [
    ("DEFINITION", r"定义|量化：|更好："),
    ("CRITERION", r"判准|【标准】|判断一件事"),
    ("BACKGROUND", r"背景|现状|时代"),
    ("AUDIENCE", r"人群|对象"),
    ("CLAIM", r"^#+\s*(?:\*+)?(?:【)?(?:论[一二三四]|论点[一二三四1234])"),
    ("DEFENSE", r"攻防|反驳|回应|接质"),
    ("WEIGHING", r"比较|结辩|价值|收束|结论"),
    ("EVIDENCE", r"数据|调查|研究|论文|案例|例子|类比|eg[：:123]|%|％"),
    ("MECHANISM", r"机理|step[12345]|过程|导致|因为|所以|从而|意味着|诠释"),
]

# These links are analyst interpretations, not claims that the evidence is verified.
CURATED = {
    "S-AI-LETTER": [
        ("更好和更真不同", "我拼的豆", "ILLUSTRATES", "类比区分文字成品质量与亲自参与的真诚，服务定义边界而非证明调查事实。"),
        ("停笔", "自己写情书的是对自我爱意", "EXPLAINS", "停笔、回想、确认、再书写的过程解释自我确认，不以术语或层数代替中间环节。"),
        ("31%", "至少一半以上", "INTERPRETED_BY", "统计后接场上诠释；百分比能否相加须核实问卷选项是否互斥，不能直接学成事实结论。"),
        ("包装 vs 真实", "AI情书的机制", "EXPLAINS", "比较场景用于解释包装与真实承诺之间的断裂，随后回扣感情成长。"),
        ("反目的、反效率", "在一个人人都被催促", "ILLUSTRATES", "金句概括愿意花时间的意义，仅计审美；支撑仍来自前面的参与过程论证。"),
        ("情书的价值不止在内容", "49%", "SUPPORTED_BY", "原稿尝试以接受端调查支撑形式意义；调查只覆盖受访者态度，不能证成全体人的必然冒犯。"),
    ],
    "S-LANGUAGE": [
        ("**人类的边界**", "人类的边界不唯一", "QUALIFIED_BY", "定义后的预攻防限定证明领域，避免把局部主张误说成所有领域。"),
        ("个体边界的拓宽", "有没有实现公共性", "EXPLAINS", "区分个体突破与整体发展，建立本稿的公共性比较条件。"),
        ("语言意味着可传承可连接", "樵夫vs李时珍", "ILLUSTRATES", "对照无记录的个体经验与可传承知识，案例要接上记录、传播、继承的机理。"),
        ("语言的边界决定思考的边界", "附近的消失", "ILLUSTRATES", "概念例子承担从未察觉到可讨论的诠释；提出词语是否是唯一因果条件尚需论证。"),
        ("语言意味着可讨论可理解", "民科vs科学家", "ILLUSTRATES", "对照构成可检验讨论的条件，不把有语言直接等同于真实科学。"),
    ],
    "S-LOVE-QUANTIFICATION": [
        ("是否增强了人类", "体重秤的出现", "ILLUSTRATES", "用正反例解释掌控判准；例子不是判准本身的经验检验。"),
        ("【论点1】", "step1", "DECOMPOSES", "亲密关系论先解释识别爱意、避免误会，再解释反馈如何指导经营。"),
        ("step2：爱的量化值", "聚餐过多", "ILLUSTRATES", "量化反馈类比接到具体行为选择，体现材料、机理、实践的关系。"),
        ("【论点2】", "step3：爱的量化", "DECOMPOSES", "岗位素质→低关爱风险→筛选/监督→减少伤害，区别于个体经营的论点分工。"),
        ("天津金色摇篮", "step2：而当这些岗位", "SUPPORTED_BY", "原稿列社会伤害案例支持风险环节；事件及数字未核验，爱与伤害的因果尚有替代解释。"),
        ("暴露问题", "不是量化在让你痛苦", "EXPLAINS", "攻防把指标暴露问题与问题造成伤害分开，随后比较短痛与积累风险。"),
    ],
}

RULE_SPECS = [
    ("T-DEF-CONTRAST", "TOPIC", "先定义并区分近邻概念", "辩题词容易把质量、真诚、效果等不同维度混同",
     "写清是什么、不是什么，区分定义与利益论证；不把己方结论预埋进定义。",
     ["analysis.definitions", "analysis.discussion_scope"], "定义是否仍让双方有可论证空间", "把‘更好’定义为己方利益最大。",
     [("S-AI-LETTER", "更好和更真不同"), ("S-LANGUAGE", "**人类的边界**")]),
    ("T-SCOPE-PUBLIC", "TOPIC", "范围与证明责任对齐", "集合概念、领域限定或反例涉及个体/整体层级",
     "明确讨论主体与重要领域，解释个体例子如何上升到集合主张，保留可被质疑的边界。",
     ["analysis.discussion_scope", "analysis.target_audience"], "有没有以个体例子直接代替整体结论", "一个运动员突破即全体知识已拓宽。",
     [("S-LANGUAGE", "有没有实现公共性")]),
    ("T-CRITERION-EXAMPLE", "TOPIC", "判准用正反例解释", "价值或比较题需要操作化胜负判断",
     "给可比较判准并以正反情景说明；双方如何获胜都应清楚，情景不替代事实证明。",
     ["analysis.judging_criteria"], "能否用同一标准评价双方", "只重复己方立场不说明如何比较。",
     [("S-LOVE-QUANTIFICATION", "是否增强了人类")]),
    ("F-DIVISION", "FRAMEWORK", "论点按功能分工", "需要多个论点共同支持主旨",
     "每论选择不同原因、作用端或受益层级；内部再分解，不能换例子重复同一机制。",
     ["arguments[].core_claim", "arguments[].explanation"], "删掉一个论点是否损失独立贡献", "个体论与群体论仅重复同一学习收益。",
     [("S-AI-LETTER", "表达端和接收端"), ("S-LOVE-QUANTIFICATION", "【论点2】")]),
    ("F-MECHANISM-CONDITION", "FRAMEWORK", "机理写中间环节与前提", "从主张推到后果的因果或条件论证",
     "解释问题如何经中间环节导致后果，写成立条件并回扣判准；层数按逻辑需要而不是固定配额。",
     ["arguments[].reasoning_nodes", "arguments[].impact"], "节点是否新增解释而非重复标题", "把主张拆成五个同义节点。",
     [("S-AI-LETTER", "停笔"), ("S-LOVE-QUANTIFICATION", "step3：爱的量化")]),
    ("F-MATERIAL-INTERPRET", "FRAMEWORK", "材料经诠释接回机理", "案例、数据、类比被用作论据",
     "标清材料类别、支持对象、诠释与不能证明的内容；有来源也不自动等于因果成立，无来源列待查。",
     ["arguments[].reasoning_nodes", "arguments[].evidence_needs"], "能否说清材料证明哪个环节而非仅贴例子", "把调查百分比不加条件相加，再泛化为所有人。",
     [("S-AI-LETTER", "31%"), ("S-LANGUAGE", "樵夫vs李时珍"), ("S-LOVE-QUANTIFICATION", "聚餐过多")]),
    ("F-ATTACK-COMPARE", "FRAMEWORK", "攻防回应后退层比较", "对方以例外、副作用或价值异议攻击主张",
     "准确复述异议，区分问题来源与工具作用，回应后比较损害与价值，回到已确认判准。",
     ["arguments[].attack_defense", "weighing"], "回应是否击中异议且没有偷换比较尺度", "只重复主张或把一切风险称滑坡。",
     [("S-LOVE-QUANTIFICATION", "不是量化在让你痛苦"), ("S-AI-LETTER", "猜疑 vs 安全感")]),
    ("A-EXPRESSION", "FRAMEWORK", "审美服务表达不替代证明", "抽象价值需要可感表达或上场骨干句",
     "允许金句、文学意象和专业术语提升表达辨识度，单独审美评价，不因其存在认定论证有效。",
     ["weighing", "arguments[].title"], "去掉修辞后推理是否仍成立", "引用名句或术语就当成机理已证明。",
     [("S-AI-LETTER", "在一个人人都被催促"), ("S-LANGUAGE", "人类的边界是前人的存档")]),
]


def blocks(text):
    start, current = None, []
    for index, line in enumerate(text.splitlines(), 1):
        if not line.strip() or (line.startswith("#") and current):
            if current:
                yield start, index - 1, "\n".join(current)
            current, start = [], None
        if line.strip():
            if start is None:
                start = index
            current.append(line)
    if current:
        yield start, len(text.splitlines()), "\n".join(current)


def annotate(path):
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    sample_id = NAMED.get(path.name, "S-" + hashlib.sha256(path.name.encode()).hexdigest()[:12].upper())
    units, relations, headings = [], [], []
    argument_ref = None
    for start, end, content in blocks(text):
        roles = [role for role, pattern in ROLE_HINTS if re.search(pattern, content, re.M)]
        heading = re.match(r"^(#+)\s*(.*)", content)
        if "CLAIM" in roles and heading:
            argument_ref = f"arg-L{start}"
        elif heading and len(heading[1]) <= 2:
            argument_ref = None
        primary = "CLAIM" if heading and "CLAIM" in roles else roles[0] if roles else "OTHER"
        unit = {"unit_id": f"u-L{start}", "argument_ref": argument_ref, "type": primary,
                "roles": roles, "text": content, "locator": {"kind": "line", "start": start, "end": end},
                "provenance": "SOURCE_EXPLICIT", "role_provenance": "AI_INFERRED",
                "interpretation": "按标题/标记识别结构作用；多重角色及证明对象需结合父级单元人工复核。",
                "review": {"status": "PENDING", "reviewer": None}, "evidence_status": "UNVERIFIED",
                "strengths": [], "limitations": ["自动结构标签是候选，不是语义质量评分。"]}
        if "EVIDENCE" in roles:
            kind = "ANALOGY" if "类比" in content else "DATA" if re.search(r"%|％|数据|调查", content) else "CASE"
            unit.update(material_kind=kind, source_as_written=content, verified_source=None)
        if heading:
            level = len(heading[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            if headings:
                relations.append({"from": unit["unit_id"], "to": headings[-1][1], "type": "STRUCTURAL_CHILD",
                                  "provenance": "SOURCE_EXPLICIT"})
            headings.append((level, unit["unit_id"]))
        elif headings:
            relations.append({"from": unit["unit_id"], "to": headings[-1][1], "type": "STRUCTURAL_CHILD",
                              "provenance": "SOURCE_EXPLICIT"})
        units.append(unit)

    def find(fragment):
        return next((unit for unit in units if fragment in unit["text"]), None)

    for left, right, relation_type, explanation in CURATED.get(sample_id, []):
        a, b = find(left), find(right)
        if a and b:
            a["interpretation"] = explanation
            a["limitations"].append("关系由 AI 分析提出，原稿事实未核验，仍待辩手复核。")
            if a != b:
                relations.append({"from": a["unit_id"], "to": b["unit_id"], "type": relation_type,
                                  "interpretation": explanation, "provenance": "AI_INFERRED",
                                  "review": {"status": "PENDING", "reviewer": None}})
    return {"annotation_version": 1, "sample_id": sample_id, "source_file": path.name,
            "source_sha256": hashlib.sha256(raw).hexdigest(), "origin": "MANUSCRIPT", "split": "METHOD",
            "authorization_ref": "USER_REQUEST_2026-11-19_LOCAL_STRUCTURE_ANNOTATION",
            "publication_authorization": "NOT_GRANTED_BY_THIS_REQUEST",
            "motion": next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem),
            "side": "正方" if "【正】" in path.name else "反方" if "【反】" in path.name else "待人工确认",
            "review_status": "DRAFT", "units": units, "relations": relations,
            "gaps": ["出处可定位不等于事实已核验。", "自动分块/角色需复核；零散记录不认定为新增正式论点。",
                     "没有显式背景/判准等单元时保留缺项，不代原作者补写。"]}


def build(source, output):
    output.mkdir(parents=True, exist_ok=False)
    samples = [annotate(path) for path in sorted(source.glob("*.md"))]
    by_id = {sample["sample_id"]: sample for sample in samples}
    rules = []
    for rule_id, agent, purpose, applies, action, paths, check, counterexample, supports in RULE_SPECS:
        evidence = []
        for sample_id, fragment in supports:
            sample = by_id[sample_id]
            unit = next((unit for unit in sample["units"] if fragment in unit["text"]), None)
            if unit is None:
                raise ValueError(f"support fragment not found: {rule_id}/{sample_id}/{fragment}")
            evidence.append({"sample_id": sample_id, "unit_id": unit["unit_id"]})
        rules.append({"rule_id": rule_id, "version": "structure-v1", "agent_type": agent, "purpose": purpose,
                      "applies_when": applies, "action": action, "output_paths": paths,
                      "self_check": check, "counterexample": counterexample, "support": evidence,
                      "epistemic_status": "AI_INFERRED", "review": {"status": "PENDING", "reviewer": None}})
    for sample in samples:
        (output / f'{sample["sample_id"]}.json').write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "structure-v1.json").write_text(json.dumps({"version": "structure-v1", "status": "DRAFT", "rules": rules},
                                                       ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "status": "DRAFT", "samples": [{"sample_id": s["sample_id"], "source_file": s["source_file"],
                                      "sha256": s["source_sha256"], "units": len(s["units"]),
                                      "relations": len(s["relations"])} for s in samples],
        "note": "Markdown 优先；同名 DOCX/PDF 导出不重复计为独立样本。本轮只授权本地标注。"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"samples": len(samples), "rules": len(rules), "output": str(output)}, ensure_ascii=False))


def validate(source, output):
    samples = {}
    for path in output.glob("S-*.json"):
        sample = json.loads(path.read_text(encoding="utf-8"))
        raw = (source / sample["source_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sample["source_sha256"]
        lines = raw.decode("utf-8-sig").splitlines()
        ids = {unit["unit_id"] for unit in sample["units"]}
        assert len(ids) == len(sample["units"])
        for unit in sample["units"]:
            loc = unit["locator"]
            assert unit["text"] == "\n".join(lines[loc["start"] - 1:loc["end"]])
        for relation in sample["relations"]:
            assert relation["from"] in ids and relation["to"] in ids
        samples[sample["sample_id"]] = sample
    rules = json.loads((output / "structure-v1.json").read_text(encoding="utf-8"))["rules"]
    for rule in rules:
        for support in rule["support"]:
            assert any(unit["unit_id"] == support["unit_id"] for unit in samples[support["sample_id"]]["units"])
    print(json.dumps({"samples_valid": len(samples), "units": sum(len(s["units"]) for s in samples.values()),
                      "relations": sum(len(s["relations"]) for s in samples.values()), "rules_valid": len(rules)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if not args.validate_only:
        build(args.source, args.output)
    validate(args.source, args.output)
