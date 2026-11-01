import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_frameworks import run


class ExtractionTests(unittest.TestCase):
    def test_markdown_trace_and_no_source_change(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sources"
            output = Path(root) / "examples"
            source.mkdir()
            draft = source / "【反】测试.md"
            content = "# 【判准】\n健康程度\n# 【论点】\n## 论点一：减少等待\n【机理】减少工序\n【案例】某餐厅\n【数据】20分钟——《调查》\n"
            draft.write_text(content, encoding="utf-8")
            manifest = run(source, output)
            self.assertEqual(len(manifest["parsed"]), 1)
            self.assertEqual(draft.read_text(encoding="utf-8"), content)
            sample = json.loads((output / manifest["parsed"][0]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(sample["position"]["text"], "反方")
            self.assertEqual(sample["arguments"][0]["locator"], "line:4")
            self.assertEqual(sample["data"][0]["locator"], "line:7")
            self.assertFalse(sample["evidence_sources"][0]["externally_verified"])

    def test_docx_and_failure_are_reported(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sources"
            output = Path(root) / "examples"
            source.mkdir()
            xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>' + escape("【论点1】共同成长") +
                '</w:t></w:r></w:p></w:body></w:document>'
            )
            with zipfile.ZipFile(source / "好稿.docx", "w") as archive:
                archive.writestr("word/document.xml", xml)
            (source / "坏稿.docx").write_bytes(b"invalid zip")
            (source / "~$暂存.docx").write_bytes(b"lock")
            manifest = run(source, output)
            self.assertEqual(len(manifest["parsed"]), 1)
            self.assertEqual(len(manifest["errors"]), 1)
            self.assertEqual(len(manifest["skipped"]), 1)
            sample = json.loads((output / manifest["parsed"][0]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(sample["arguments"][0]["locator"], "word/document.xml:paragraph:1")
            self.assertIn("BadZipFile", manifest["errors"][0]["reason"])

    def test_pdf_text_layer(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf 未安装")
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sources"
            source.mkdir()
            document = pymupdf.open()
            document.new_page().insert_text((72, 72), "argument and evidence")
            document.save(source / "draft.pdf")
            document.close()
            manifest = run(source, Path(root) / "examples")
            self.assertFalse(manifest["errors"])
            sample = json.loads((Path(root) / "examples" / manifest["parsed"][0]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(sample["raw_units"][0]["locator"], "page:1:line:1")

    def test_image_only_pdf_reports_error(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf 未安装")
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sources"
            source.mkdir()
            document = pymupdf.open()
            document.new_page()
            document.save(source / "扫描稿.pdf")
            document.close()
            manifest = run(source, Path(root) / "examples")
            self.assertFalse(manifest["parsed"])
            self.assertIn("OCR", manifest["errors"][0]["reason"])

    def test_converted_markdown_title_sections_and_missing_images(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sources"
            source.mkdir()
            (source / "garbled.md").write_text(
                '<img src="assets/missing.png" />\n# 如果爱可以量化，是人类的幸运——框架\n'
                '## 【标准】\n判断幸运/不幸：是否更有掌控\n'
                '## 【论点1】掌控关系\n<u>step1：减少误会</u>\n'
                '## 攻防\n- <u>量化可能引发攀比</u>\n', encoding="utf-8"
            )
            manifest = run(source, Path(root) / "examples")
            sample = json.loads((Path(root) / "examples" / manifest["parsed"][0]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(sample["debate_topic"]["locator"], "line:2")
            self.assertEqual(sample["position"]["locator"], "line:2")
            self.assertEqual(len(sample["arguments"]), 1)
            self.assertEqual(sample["mechanisms"][0]["locator"], "line:6")
            self.assertEqual(sample["judging_criteria"][0]["locator"], "line:4")
            self.assertEqual(sample["rebuttals"][0]["locator"], "line:8")
            self.assertFalse(sample["image_gaps"][0]["available"])


if __name__ == "__main__":
    unittest.main()
