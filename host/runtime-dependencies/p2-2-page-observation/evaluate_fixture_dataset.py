"""Labeled synthetic evidence only. Known positives stay in the accuracy denominator."""
import copy
import json

from observation_identity import derive_page, search_elements
from test_identity import observation
from test_support import frame_fixture


def dataset():
    samples = []
    # Labels/expectations are evaluator-side annotations, not an imported Agent mapping.
    for i, label in enumerate(['Room 1','Room 101','Room 102','ROOM101','房间 101','房间 102']):
        for value in (20,80):
            samples.append({'sample_id': f'positive-{i}-{value}', 'frame': frame_fixture(value=value,entity=label),
                            'expected_status':'KNOWN', 'expected_labels':[label], 'expected_visible_slider_ids':['0.1']})
    for label in ['Settings','Controls','Roommate','Room','loading','101']:
        samples.append({'sample_id':'reject-'+str(len(samples)), 'frame':frame_fixture(entity=label),
                        'expected_status':'UNKNOWN', 'expected_labels':[], 'expected_visible_slider_ids':['0.1']})
    hidden = frame_fixture(); hidden['tree']['nodes'][-1]['visible'] = False
    samples.append({'sample_id':'offscreen-slider','frame':hidden,'expected_status':'KNOWN',
                    'expected_labels':['Room 101'],'expected_visible_slider_ids':[]})
    popup = frame_fixture(); popup['navigation_context']['popup'] = 'same-app-dialog'
    samples.append({'sample_id':'popup-context','frame':popup,'expected_status':'KNOWN',
                    'expected_labels':['Room 101'],'expected_visible_slider_ids':['0.1']})
    return samples


def evaluate():
    rows = []; expected_targets = retrieved_targets = correct_targets = 0
    positives = correct_positives = unknown_positives = refusals = correct_refusals = 0
    for sample in dataset():
        obs = observation(copy.deepcopy(sample['frame'])); page = derive_page(obs,entity_types=['room'])
        found = search_elements(page,role='slider')
        actual = {item['node_local_id'] for item in found['items']}
        expected = set(sample['expected_visible_slider_ids'])
        expected_targets += len(expected); retrieved_targets += len(actual); correct_targets += len(expected & actual)
        labels = [e['label'] for e in page['entities']]
        correct = page['identity_status'] == sample['expected_status'] and labels == sample['expected_labels']
        if sample['expected_status'] == 'KNOWN':
            positives += 1; correct_positives += int(correct); unknown_positives += int(page['identity_status'] != 'KNOWN')
        else: refusals += 1; correct_refusals += int(correct)
        rows.append({'sample_id':sample['sample_id'],'expected':sample['expected_status'],'observed':page['identity_status'],
                     'correct':correct,'labels':labels,'visible_targets_correct':actual == expected,
                     'template_id':page['template_id'],'page_instance_id':page['page_instance_id']})
    return {'channel':'LABELED_SYNTHETIC_DTO_NOT_ANDROID','samples':len(rows),'positive_samples':positives,
            'correct_positive_samples':correct_positives,'positive_unknown_samples':unknown_positives,
            'positive_accuracy':correct_positives/positives,'positive_rejection_rate':unknown_positives/positives,
            'rejection_samples':refusals,'correct_rejections':correct_refusals,
            'visible_target_expected':expected_targets,'visible_target_returned':retrieved_targets,
            'visible_target_recall':correct_targets/expected_targets if expected_targets else None,
            'visible_target_precision':correct_targets/retrieved_targets if retrieved_targets else None,
            'model_calls':0,'device_observations':0,'device_actions':0,'rows':rows}


if __name__ == '__main__': print(json.dumps(evaluate(),ensure_ascii=True,indent=2))
