"""Export a project Markdown document to a readable DOCX without extra packages."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("w", W)
ET.register_namespace("r", R)


def tag(name: str) -> str:
    return f"{{{W}}}{name}"


def add_text(paragraph: ET.Element, text: str, bold: bool = False, code: bool = False) -> None:
    if not text:
        return
    run = ET.SubElement(paragraph, tag("r"))
    properties = ET.SubElement(run, tag("rPr"))
    ET.SubElement(properties, tag("rFonts"), {tag("ascii"): "Consolas" if code else "Calibri", tag("eastAsia"): "Microsoft YaHei"})
    if bold:
        ET.SubElement(properties, tag("b"))
    if code:
        ET.SubElement(properties, tag("color"), {tag("val"): "334155"})
    content = ET.SubElement(run, tag("t"))
    content.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    content.text = text


def add_inline(paragraph: ET.Element, line: str) -> None:
    # Preserve bold and inline code without treating markdown as Word source text.
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line):
        if part.startswith("**") and part.endswith("**"):
            add_text(paragraph, part[2:-2], bold=True)
        elif part.startswith("`") and part.endswith("`"):
            add_text(paragraph, part[1:-1], code=True)
        else:
            add_text(paragraph, part)


def paragraph(body: ET.Element, text: str, style: str = "Normal", indent: int = 0, code: bool = False) -> None:
    node = ET.SubElement(body, tag("p"))
    settings = ET.SubElement(node, tag("pPr"))
    ET.SubElement(settings, tag("pStyle"), {tag("val"): style})
    ET.SubElement(settings, tag("spacing"), {tag("after"): "100", tag("line"): "360", tag("lineRule"): "auto"})
    if indent:
        ET.SubElement(settings, tag("ind"), {tag("left"): str(indent)})
    if code:
        add_text(node, text, code=True)
    else:
        add_inline(node, text)


def document_xml(markdown: str) -> bytes:
    root = ET.Element(tag("document"))
    body = ET.SubElement(root, tag("body"))
    fenced = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            paragraph(body, raw, "Code", indent=420, code=True)
        elif not line or line == "---":
            continue
        elif line.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                paragraph(body, match.group(2), "Heading" + str(min(len(match.group(1)), 3)))
            else:
                paragraph(body, line)
        elif re.match(r"^[-*]\s+", line):
            paragraph(body, "• " + re.sub(r"^[-*]\s+", "", line), indent=420)
        elif re.match(r"^\d+[.]\s+", line):
            paragraph(body, line, indent=420)
        else:
            paragraph(body, line.replace("  ", " "))
    section = ET.SubElement(body, tag("sectPr"))
    ET.SubElement(section, tag("pgSz"), {tag("w"): "11906", tag("h"): "16838"})
    ET.SubElement(section, tag("pgMar"), {
        tag("top"): "1440", tag("right"): "1440", tag("bottom"): "1440", tag("left"): "1440",
        tag("header"): "708", tag("footer"): "708", tag("gutter"): "0",
    })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


STYLES = """<?xml version="1.0" encoding="utf-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:rPr><w:sz w:val="22"/><w:rFonts w:eastAsia="Microsoft YaHei"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="300" w:after="160"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="17365D"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="27"/><w:color w:val="1F4E79"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/>
    <w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="19"/></w:rPr></w:style>
</w:styles>"""


def export(markdown_path: Path, docx_path: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8-sig")
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>""")
        archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""")
        archive.writestr("word/_rels/document.xml.rels", """<?xml version="1.0" encoding="utf-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""")
        archive.writestr("word/document.xml", document_xml(text))
        archive.writestr("word/styles.xml", STYLES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 Markdown 生成带标题层级的 DOCX")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.source, args.destination)
    print(f"已生成：{args.destination}")
