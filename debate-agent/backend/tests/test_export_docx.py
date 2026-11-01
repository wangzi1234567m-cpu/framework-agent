import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from export_docx import export


class DocxExportTests(unittest.TestCase):
    def test_chinese_heading_list_and_final_paragraph(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.md"
            target = Path(directory) / "result.docx"
            source.write_text("# 辩论稿\n\n## 审核\n- **人工确认**后使用\n\n最后一段。\n", encoding="utf-8")
            export(source, target)
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                root = ET.fromstring(archive.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            texts = [node.text for node in root.findall(".//w:t", namespace)]
            self.assertIn("辩论稿", texts)
            self.assertIn("人工确认", texts)
            self.assertIn("最后一段。", texts)
            self.assertTrue(root.findall(".//w:pStyle[@w:val='Heading1']", namespace))


if __name__ == "__main__":
    unittest.main()
