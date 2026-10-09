import tempfile
import json
import subprocess
import sys
import unittest
from pathlib import Path
from task5_documents import render_markdown, proportion, bounds


class DocumentTests(unittest.TestCase):
    def test_actual_cli_defines_renderer_before_creating_reports(self):
        from evaluation_framework import ratio
        from task5_protocol import latency
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=dict(task1=dict(model='synthetic-model-not-live',summary=dict(passScored=ratio(180,180),latencyAll=latency([1]*180,180))),
                      task3=dict(normalCompletion=6,safeStops=22))
            (root/'historical.json').write_text(json.dumps(data),encoding='utf-8')
            (root/'summary.json').write_text(json.dumps(dict(softwarePipeline='PASS',evidenceFiles=1)),encoding='utf-8')
            run=subprocess.run([sys.executable,str(Path(__file__).with_name('task5_documents.py')),'--bundle',str(root)],capture_output=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr.decode('utf-8',errors='replace'))
            self.assertEqual(len(list((root/'reports').glob('*.pdf'))),2)

    def test_unknown_ratio_is_not_zero(self):
        self.assertEqual(proportion(dict(numerator=0,denominator=0,value=None)),'未测')
        self.assertEqual(proportion(dict(numerator=1,denominator=2,value=.5)),'1/2 (50.0%)')

    def test_zero_error_interval_still_has_upper_bound(self):
        self.assertEqual(bounds(dict(wilson95=None)),'未测')
        self.assertIn('4.1%',bounds(dict(wilson95=[0,.041])))

    def test_pdf_render_has_chinese_table_pages_and_text(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.pdf'
            render_markdown('# 中文报告\n\n说明\n\n|指标|结果|\n|---|---|\n|完整任务|未测|\n\n<!-- pagebreak -->\n\n## 另一页\n\n失败保留。',out)
            pdf=PdfReader(out);self.assertEqual(len(pdf.pages),2)
            text=''.join(p.extract_text() for p in pdf.pages)
            self.assertIn('完整任务',text);self.assertIn('未测',text)
