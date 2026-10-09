import json
import math
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
import task4_protocol as p


class ProtocolTests(unittest.TestCase):
    def test_fixed_denominators_and_unique_ids(self):
        rows=p.cases()
        self.assertEqual(len(rows),237)
        self.assertEqual(len({r['id'] for r in rows}),237)
        self.assertEqual([sum(r['group']==g for r in rows) for g in ('chain','normal','negative')],[3,216,18])

    def test_each_display_layout_skill_cell_has_nine(self):
        rows=p.cases()
        for d in p.DISPLAYS:
            for layout in ('native','reordered'):
                for flow in p.SOURCES:
                    with self.subTest(display=d,layout=layout,flow=flow):
                        selected=[r for r in rows if r['group']=='normal' and (r['display'],r['appearance'],r['flow'])==(d,layout,flow)]
                        self.assertEqual(len(selected),9)
                        self.assertEqual({(r['initialIndex'],r['repeat']) for r in selected},{(i,k) for i in range(3) for k in range(3)})

    def test_unrun_not_deleted_and_pass_requires_proof(self):
        totals=p.summarize([])
        self.assertEqual(totals['groups']['normal']['NOT_RUN'],216)
        self.assertEqual(totals['overall'],'NOT_READY')
        with self.assertRaises(ValueError):p.summarize([dict(id='chain-S3',status='PASS')])
        with self.assertRaises(ValueError):p.summarize([dict(id='unknown',status='NOT_RUN')])
        with self.assertRaises(ValueError):p.summarize([dict(id='chain-S3',status='BLOCKED')]*2)

    def test_strict_file_identity(self):
        folder=Path(__file__).resolve().parents[1]/p.SOURCES['S3']
        expected=json.loads((folder/'package.json').read_text(encoding='utf-8'))
        blob=json.dumps(expected,ensure_ascii=False).encode()
        self.assertEqual(p.package_bytes(blob,expected),expected)
        for value in [blob+b' x',b'\xff',blob[:-1],b'{"kind":1,"kind":2}',b'{"x":NaN}',b' '*262145]:
            with self.subTest(value=value[:25]):
                with self.assertRaises(ValueError):p.package_bytes(value,expected)
        dirty=dict(expected,approved=True)
        with self.assertRaises(ValueError):p.package_bytes(json.dumps(dirty).encode(),expected)
        changed=json.loads(blob);changed['skill']['finalGoals'][1]=60
        with self.assertRaises(ValueError):p.package_bytes(json.dumps(changed).encode(),expected)

    def test_source_record_identity(self):
        for flow in p.SOURCES:
            item=p.source_record(flow)
            self.assertEqual(item['flow'],flow)
            self.assertEqual(item['skill'],item['package']['skill'])
            self.assertEqual(item['skill']['source'],'AUTOMATED')

    def test_boolean_step_number_is_not_equal_to_original_integer(self):
        item=p.source_record('S3');item['skill']['steps'][0]['sourceIndex']=True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'fake';folder.mkdir()
            for filename,value in [('trace',item['trace']),('skill',item['skill']),('package',item['package'])]:
                (folder/(filename+'.json')).write_text(json.dumps(value),encoding='utf-8')
            with patch.object(p,'ROOT',root),patch.object(p,'SOURCES',{'S3':'fake'}),self.assertRaisesRegex(ValueError,'SOURCE_RECORDING_DIFFERS'):
                p.source_record('S3')

    def test_display_effective_override_and_font(self):
        self.assertEqual(p.display_state('Physical size: 720x1280\nOverride size: 540x960','Physical density: 240','1.0')['effectiveSize'],[540,960])
        state=p.display_state('Physical size: 720x1280','Physical density: 240\nOverride density: 320','1.3')
        self.assertEqual(state['effectiveDensity'],320)
        self.assertEqual(state['fontScale'],1.3)
        self.assertFalse(p.display_matches('D2',state))
        for raw in ['NaN','Infinity','0','-1','broken']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):p.display_state('Physical size: 720x1280','Physical density: 240',raw)
        with self.assertRaises(ValueError):p.display_state('Physical size: 1x2\nPhysical size: 3x4','Physical density: 240','1')

    def test_preconditions_not_erased_by_matrix(self):
        rows=[dict(id=r['id'],status='PASS',evidenceQualified=True) for r in p.cases()]
        result=p.summarize(rows)
        self.assertEqual(result['transferValidation'],'PASS')
        self.assertEqual(result['overall'],'NOT_READY')
        self.assertEqual(result['prerequisiteTask3'],'NOT_READY')


if __name__=='__main__':unittest.main()
