import copy
import unittest
from semantic_complex_cases import cases,score
from semantic_parameter_calls import build_request,validate_calls


class ComplexEvaluationTests(unittest.TestCase):
    def test_frozen_case_shape_labels_bilingual_and_long_sequences(self):
        rows=cases();self.assertEqual(len(rows),60)
        self.assertEqual(len({r['caseId'] for r in rows}),60)
        self.assertEqual(sum(r['language']=='zh' for r in rows),30)
        self.assertEqual(sum(r['language']=='en' for r in rows),30)
        for row in rows:
            build_request(row['text'],row['skills'])
            data=dict(status='invoke' if row['expectedCalls'] is not None else 'clarify',
                      calls=row['expectedCalls'] or [],message='Label check, not an LLM result')
            validate_calls(data,row['skills']);self.assertTrue(score(row,data)['correct'])
        self.assertTrue({6,8,12}.issubset({len(r['expectedCalls'] or []) for r in rows}))
    def test_final_value_alone_cannot_pass_ordered_task(self):
        row=next(r for r in cases() if r['caseId']=='repeat-en')
        self.assertFalse(score(row,dict(status='invoke',calls=row['expectedCalls'][-1:]))['correct'])
    def test_reverse_duplicate_skip_extra_and_parameter_errors_fail(self):
        row=next(r for r in cases() if r['caseId']=='eight-zh');gold=row['expectedCalls']
        mutations=[gold[::-1],gold[:-1],gold+gold[:1]]
        wrong=copy.deepcopy(gold);wrong[0]['args']['percent']=40;mutations.append(wrong)
        for calls in mutations:self.assertFalse(score(row,dict(status='invoke',calls=calls))['correct'])
    def test_any_action_for_negative_is_false_invoke(self):
        negative=next(r for r in cases() if r['caseId']=='negated-only-en')
        positive=next(r for r in cases() if r['caseId']=='simple-en')
        result=score(negative,dict(status='invoke',calls=positive['expectedCalls']))
        self.assertFalse(result['correct']);self.assertTrue(result['falseInvoke'])
        self.assertFalse(score(positive,dict(status='clarify',calls=[]))['correct'])


if __name__=='__main__':unittest.main()
