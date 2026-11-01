"""Extract traceable draft evidence without rewriting or validating source claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


EXTENSIONS = {".md", ".docx", ".pdf"}
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SECTION_RE = re.compile(r"【(定义|背景|现状|判准|标准|论点|攻防|自由辩|价值|时间和环节分配)】")
ARGUMENT_RE = re.compile(r"^(?:【?论点[一二三四五六七八九十\d]+[】、：:]?|论[一二三四五六七八九十]+[：:]|[1-9][.、]【[^】]+】|[1-9][.、]促进)")
MECHANISM_RE = re.compile(r"【(?:机理|逻辑链|比较|方法论)】|^(?:机理\d*|逻辑链|step\s*\d*|[1-9][.][1-9])\s*[：:、]?|[—-]{1,2}>")
CASE_RE = re.compile(r"【(?:案例|情景|场景)】|(?:案例|情景|场景|eg\d*|例子|类比)\s*[：:]")
DATA_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万(?:人|家|元|份)?|亿(?:人|元)?|分钟|小时|元|人|份|岁|年|个月)")
SOURCE_RE = re.compile(r"《[^》\n]{2,90}》|https?://[^\s)）\]]+")
PLACEHOLDER_RE = re.compile(r"^(?:【[^】]+】\s*)?(?:查几份|待补|xxx|1\.3\s*$|数据\s*[：:]\s*$)")
IMAGE_RE = re.compile(r"(?:!\[[^]]*\]\(|<img\b[^>]*\bsrc=[\"'])(assets/[^)\"']+)")


def document_units(path: Path) -> list[dict]:
    if path.suffix.lower() == ".md":
        text = path.read_text(encoding="utf-8-sig")
        return [{"locator": f"line:{i}", "text": line} for i, line in enumerate(text.splitlines(), 1)]
    if path.suffix.lower() == ".docx":
        units = []
        with zipfile.ZipFile(path) as archive:
            parts = ["word/document.xml"] + sorted(
                name for name in archive.namelist()
                if re.fullmatch(r"word/(?:header|footer)\d+\.xml|word/(?:footnotes|endnotes|comments)\.xml", name)
            )
            for part in parts:
                if part not in archive.namelist():
                    continue
                root = ElementTree.fromstring(archive.read(part))
                for index, paragraph in enumerate(root.iter(WORD_NS + "p"), 1):
                    text = "".join(node.text or "" for node in paragraph.iter(WORD_NS + "t"))
                    units.append({"locator": f"{part}:paragraph:{index}", "text": text})
        return units
    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError("PDF 解析需要 pymupdf：pip install pymupdf") from exc
        units = []
        with pymupdf.open(path) as document:
            for page_no, page in enumerate(document, 1):
                for line_no, line in enumerate(page.get_text(sort=True).splitlines(), 1):
                    units.append({"locator": f"page:{page_no}:line:{line_no}", "text": line})
        if not any(unit["text"].strip() for unit in units):
            raise ValueError("PDF 无可提取文字层；需要 OCR，本阶段未进行 OCR")
        return units
    raise ValueError(f"不支持的文件格式：{path.suffix}")


def extract(path: Path, source_root: Path) -> dict:
    units = document_units(path)
    if not any(unit["text"].strip() for unit in units):
        raise ValueError("文档没有可提取的正文文字")
    source_name = path.name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    section = None
    argument = None
    arguments = []
    fields = {key: [] for key in ("judging_criteria", "core_claims", "mechanisms", "cases", "data", "evidence_sources", "rebuttals")}
    warnings = []
    image_gaps = []
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            if any(name.startswith("word/media/") for name in archive.namelist()):
                warnings.append("DOCX 包含内嵌媒体；图片中的文字未进行 OCR")
    for unit in units:
        text = unit["text"]
        if text.startswith("![") and "data:image/" in text:
            unit["text"] = "[内嵌图片数据；文字未提取，参见原稿对应行]"
            warnings.append(f"{unit['locator']}：内嵌图片未解析")
            continue
        if path.suffix.lower() == ".md":
            for image in IMAGE_RE.findall(text):
                gap = {"locator": unit["locator"], "path": image, "available": (path.parent / image).is_file()}
                image_gaps.append(gap)
                if not gap["available"]:
                    warnings.append(f"{unit['locator']}：引用图片不存在，未解析：{image}")
        clean = re.sub(r"<[^>]+>", "", text)
        clean = re.sub(r"^[\s#*•◦.\-]+", "", clean).strip()
        if not clean:
            continue
        marker = SECTION_RE.search(clean)
        if marker and clean == f"【{marker.group(1)}】":
            section = marker.group(1)
            if section != "论点":
                argument = None
        elif text.lstrip().startswith("#") and clean.startswith(("定义", "背景", "现状", "攻防", "自由辩", "价值")):
            section = next(name for name in ("定义", "背景", "现状", "攻防", "自由辩", "价值") if clean.startswith(name))
            argument = None
        elif clean in ("定义", "背景", "现状", "攻防", "自由辩", "价值"):
            section = clean
            argument = None
        elif ARGUMENT_RE.match(clean) and not re.match(r"^论点\d+预反驳", clean) and (
            section != "攻防" or clean.startswith(("论点", "【论点", "论一", "论二"))
        ):
            section = "论点"
            if arguments and arguments[-1]["text"] == clean:
                argument = arguments[-1]
                argument.setdefault("duplicate_locators", []).append(unit["locator"])
            else:
                argument = {"text": clean, "locator": unit["locator"], "mechanisms": [], "cases": [], "data": []}
                arguments.append(argument)
                fields["core_claims"].append({"text": clean, "locator": unit["locator"]})
        unit["section"] = section
        unit["argument_locator"] = argument["locator"] if argument else None
        ref = {"text": clean, "locator": unit["locator"]}
        if section in ("判准", "标准") and not marker and (
            re.match(r"^[12][.、]", clean) or clean.startswith(("判断", "是否"))
        ):
            fields["judging_criteria"].append(ref)
        if PLACEHOLDER_RE.search(clean):
            warnings.append(f"{unit['locator']}：疑似占位内容")
            continue
        if MECHANISM_RE.search(clean) and not ARGUMENT_RE.match(clean):
            fields["mechanisms"].append(ref)
            if argument:
                argument["mechanisms"].append(unit["locator"])
        if CASE_RE.search(clean):
            fields["cases"].append(ref)
            if argument:
                argument["cases"].append(unit["locator"])
        if DATA_RE.search(clean) and len(clean) > 12 and not clean.startswith("http"):
            fields["data"].append(ref)
            if argument:
                argument["data"].append(unit["locator"])
        sources = list(dict.fromkeys(SOURCE_RE.findall(clean)))
        if sources:
            fields["evidence_sources"].append({**ref, "mentioned_sources": sources, "externally_verified": False})
        if section == "攻防" and len(clean) > 6 and not marker:
            fields["rebuttals"].append(ref)
    heading = next(
        ((unit["locator"], unit["text"].lstrip("# ").strip())
         for unit in units if re.match(r"^\s*#\s+\S", unit["text"]) and len(unit["text"]) < 180),
        None,
    ) if path.suffix.lower() == ".md" else None
    title = heading[1] if heading else next((u["text"].strip() for u in units if u["text"].strip()), None)
    title_locator = heading[0] if heading else ("word/document.xml:paragraph:1" if path.suffix.lower() == ".docx" else "filename")
    if title and (title.startswith("![") or title.startswith("<img") or len(title) > 180 or title in ("【定义】", "【背景】")):
        title = None
    # A short document opening may only name an event; the file name is always preserved.
    position = {"text": "反方", "basis": "标题/文件名中的【反】", "locator": title_locator if title and "【反】" in title else "filename", "kind": "原稿标注"} if "【反】" in (title or "") or "【反】" in source_name else None
    if position is None:
        stated = title or source_name
        if "是人类的幸运" in stated:
            position = {"text": "如果爱可以量化，是人类的幸运", "basis": stated, "locator": title_locator if title else "filename", "kind": "原稿表述"}
        elif "传统就业比OPC模式更能实现职业价值" in stated.replace(" ", ""):
            position = {"text": "传统就业更能实现职业价值", "basis": stated, "locator": title_locator if title else "filename", "kind": "原稿表述"}
        elif "更应该采取“利益”视角" in stated:
            position = {"text": "更应该采取利益视角", "basis": stated, "locator": "filename", "kind": "原稿表述"}
        elif "消费者福利的提升" in stated:
            position = {"text": "是消费者福利的提升", "basis": stated, "locator": "filename", "kind": "原稿表述"}
        elif "容错率" in source_name and len(arguments) >= 2 and all(
            "变低" in entry["text"] or "下降" in entry["text"] for entry in arguments[:2]
        ):
            position = {
                "text": "变低", "basis": [entry["text"] for entry in arguments[:2]],
                "locator": [entry["locator"] for entry in arguments[:2]], "kind": "AI推断_待用户确认",
            }
    topic_from_title = title and len(title) > 12 and path.suffix.lower() != ".pdf"
    return {
        "schema_version": 1,
        "provenance": {
            "source_path": "../" + str(path.relative_to(source_root)).replace("\\", "/"),
            "sha256": digest,
            "format": path.suffix.lower(),
            "unit_type": "原文件行" if path.suffix.lower() == ".md" else "Word XML 段落" if path.suffix.lower() == ".docx" else "PDF 页面文字行",
            "original_unchanged": True,
        },
        "debate_topic": {"text": title if topic_from_title else path.stem, "basis": "正文标题" if topic_from_title else "文件名；需对照正文确认", "locator": title_locator if topic_from_title else "filename"},
        "declared_title": title,
        "position": position,
        "extraction_status": "parsed_unverified",
        "classification_note": "字段为规则匹配的原稿片段候选，不代表事实核验；无标签的论证或跨行来源可能遗漏。",
        "judging_criteria": fields["judging_criteria"],
        "core_claims": fields["core_claims"],
        "arguments": arguments,
        "mechanisms": fields["mechanisms"],
        "cases": fields["cases"],
        "data": fields["data"],
        "evidence_sources": fields["evidence_sources"],
        "rebuttals": fields["rebuttals"],
        "raw_units": units,
        "warnings": sorted(set(warnings)),
        "image_gaps": image_gaps,
    }


def run(source_root: Path, output_dir: Path) -> dict:
    source_root = source_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "source_root": str(source_root), "parsed": [], "skipped": [], "errors": []}
    for path in sorted(source_root.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if path.name.startswith("~$"):
            manifest["skipped"].append({"source": path.name, "reason": "Word 临时锁文件，不是正式稿件"})
            continue
        filename = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16] + ".json"
        try:
            result = extract(path, source_root)
            (output_dir / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest["parsed"].append({"source": path.name, "output": filename, "sha256": result["provenance"]["sha256"]})
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            manifest["errors"].append({"source": path.name, "reason": f"{type(exc).__name__}: {exc}"})
    by_stem = {}
    for entry in manifest["parsed"]:
        result = json.loads((output_dir / entry["output"]).read_text(encoding="utf-8"))
        title = result["debate_topic"]["text"]
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", title.removesuffix("——框架"))
        by_stem.setdefault(normalized, []).append(entry["source"])
    manifest["possible_same_draft_exports"] = [
        {"files": names, "kind": "AI 推断：正文标题相近或同名，不能据此认定内容完全相同"}
        for names in by_stem.values() if len(names) > 1
    ]
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="扫描项目上一级的框架稿，生成可追溯 JSON")
    parser.add_argument("--source", type=Path, default=project.parent, help="仅扫描此目录下的文件，不递归")
    parser.add_argument("--output", type=Path, default=project / "backend/knowledge/examples")
    args = parser.parse_args()
    manifest = run(args.source, args.output)
    print(f"已解析 {len(manifest['parsed'])} 份；跳过 {len(manifest['skipped'])} 份；失败 {len(manifest['errors'])} 份")
    for error in manifest["errors"]:
        print(f"解析失败 {error['source']}：{error['reason']}", file=sys.stderr)
    return 1 if manifest["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
