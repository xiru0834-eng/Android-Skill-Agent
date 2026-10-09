"""Strict serialized observation contract; evidence is not device authority."""
import re
from observation_capture import VALID, _metadata
from observation_tree import copy_tree, identifier, plain_copy, require

OBS_FIELDS = {'kind', 'schema_version', 'observation_id', 'environment', 'scope_hash',
              'host_device_id', 'boot_session_id', 'observer_session_id', 'window_before', 'window_after',
              'started_elapsed_ms', 'ended_elapsed_ms', 'deadline_elapsed_ms', 'capture_status', 'attempts',
              'tree', 'screenshot', 'navigation_context', 'consistency', 'channel', 'producer_version',
              'known_scope', 'limitations', 'execution_authority', 'budget'}


def _sha(value, nullable=False):
    return (nullable and value is None) or (type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None)


def _id(value):
    return identifier(value) and re.fullmatch(r'[A-Za-z0-9_.:-]+', value) is not None


def _budget(value, obs):
    keys = {'session_id','scope_hash','environment_id','status','started_ms','deadline_ms','spent','limits',
            'execution_authority','enforcement'}
    require(type(value) is dict and set(value) == keys and value['execution_authority'] is False
            and value['enforcement'] == 'LOCAL_ACCOUNTING_NOT_RUNTIME_INTEGRATION'
            and value['scope_hash'] == obs['scope_hash'] and value['environment_id'] == obs['environment']['environment_id']
            and _id(value['session_id']) and identifier(value['status']), 'INVALID_OBSERVATION')
    require(all(type(value[k]) is int and value[k] >= 0 for k in ('started_ms','deadline_ms'))
            and value['deadline_ms'] >= obs['deadline_elapsed_ms'], 'INVALID_OBSERVATION')
    for key in ('spent','limits'):
        require(type(value[key]) is dict and set(value[key]) == {'observations','actions','model_requests','storage_bytes'}
                and all(type(v) is int and 0 <= v <= 67108864 for v in value[key].values()), 'INVALID_OBSERVATION')


def _navigation(nav):
    require(type(nav) is dict and set(nav) == {'tab','popup','expanded','entry','visible_slice','page_hint'}, 'INVALID_OBSERVATION')
    require(all(identifier(nav[k], nullable=True) for k in ('tab','popup','entry','visible_slice','page_hint'))
            and type(nav['expanded']) is list and len(nav['expanded']) <= 128
            and all(identifier(v) for v in nav['expanded']), 'INVALID_OBSERVATION')


def _pair(pair):
    require(type(pair) is dict and set(pair) == {'pairing_status','visual_content_check','tree_a_uptime','tree_b_uptime'}, 'INVALID_OBSERVATION')
    for key in ('tree_a_uptime','tree_b_uptime'):
        require(type(pair[key]) is list and len(pair[key]) == 2 and all(type(t) is int and t >= 0 for t in pair[key]), 'INVALID_OBSERVATION')
    a, b = pair['tree_a_uptime'], pair['tree_b_uptime']
    require(a[0] <= a[1] <= b[0] <= b[1] and b[1] - a[0] <= 250, 'INVALID_OBSERVATION')


def _screenshot(packet, obs):
    fields = {'request_id','status','window_id','display_id','host_device_id','boot_session_id','clock_domain',
              'captured_uptime_ms','callback_elapsed_ms','evidence_ref','sha256','dimensions','error_code','content_check'}
    require(type(packet) is dict and set(packet) == fields and _id(packet['request_id'])
            and packet['status'] in ('AVAILABLE','FAILED','UNAVAILABLE')
            and all(type(packet[k]) is int and packet[k] >= 0 for k in ('window_id','display_id'))
            and packet['window_id'] == obs['window_after']['window_id'] and packet['display_id'] == obs['window_after']['display_id']
            and packet['host_device_id'] == obs['host_device_id'] and packet['boot_session_id'] == obs['boot_session_id'], 'INVALID_OBSERVATION')
    require(type(packet['callback_elapsed_ms']) is int and obs['started_elapsed_ms'] <= packet['callback_elapsed_ms'] <= obs['ended_elapsed_ms']
            and identifier(packet['error_code'], nullable=True), 'INVALID_OBSERVATION')
    if packet['status'] == 'AVAILABLE':
        pair = obs['consistency']
        require(packet['clock_domain'] == 'uptimeMillis' and type(packet['captured_uptime_ms']) is int
                and pair['tree_a_uptime'][0] <= packet['captured_uptime_ms'] <= pair['tree_b_uptime'][1]
                and identifier(packet['evidence_ref']) and _sha(packet['sha256'])
                and type(packet['dimensions']) is list and len(packet['dimensions']) == 2
                and all(type(v) is int and 0 < v <= 16384 for v in packet['dimensions']), 'INVALID_OBSERVATION')
        check = packet['content_check']
        if check is not None:
            require(type(check) is dict and set(check) == {'source','facts'}
                    and check['source'] == 'OFFLINE_SIMULATED_VISUAL_CHECK'
                    and type(check['facts']) is list and 0 < len(check['facts']) <= 128, 'INVALID_OBSERVATION')
            index = {n['node_local_id']: n for n in obs['tree']['nodes']}
            for fact in check['facts']:
                require(type(fact) is dict and set(fact) == {'node_local_id','field','value'}
                        and fact['node_local_id'] in index and fact['field'] in ('text','checked','range.value'), 'INVALID_OBSERVATION')
                n = index[fact['node_local_id']]
                actual = n['range']['value'] if fact['field'] == 'range.value' and n['range'] is not None else n.get(fact['field'])
                require(type(actual) is type(fact['value']) and actual == fact['value'], 'INVALID_OBSERVATION')


def validate_observation(value):
    obs = plain_copy(value)
    require(type(obs) is dict and set(obs) == OBS_FIELDS and obs['kind'] == 'PageObservation'
            and obs['schema_version'] == '1.0' and obs['producer_version'] == 'P2_2_1.0'
            and obs['channel'] == 'OFFLINE_CALLBACK_SIMULATION'
            and obs['execution_authority'] is False and _id(obs['observation_id']), 'INVALID_OBSERVATION')
    require(type(obs['environment']) is dict and set(obs['environment']) == {
        'app_package', 'app_build', 'environment_id', 'ui_revision', 'domain'}, 'INVALID_OBSERVATION')
    require(all(identifier(v) for v in obs['environment'].values()), 'INVALID_OBSERVATION')
    require(type(obs['scope_hash']) is str and re.fullmatch('[0-9a-f]{64}', obs['scope_hash']), 'INVALID_OBSERVATION')
    for field in ('started_elapsed_ms', 'ended_elapsed_ms', 'deadline_elapsed_ms'):
        require(type(obs[field]) is int and obs[field] >= 0, 'INVALID_OBSERVATION')
    require(type(obs['capture_status']) is str and identifier(obs['capture_status']), 'INVALID_OBSERVATION')
    require(type(obs['attempts']) is list and 0 < len(obs['attempts']) <= 2, 'INVALID_OBSERVATION')
    require(type(obs['limitations']) is list and set(obs['limitations']) == {'NOT_ATOMIC_FRAME','NOT_LIVE_ANDROID_EVIDENCE'}, 'INVALID_OBSERVATION')
    require(obs['known_scope'] in ('NO_VALID_OBSERVATION','PUBLIC_TREE_COMPLETE','PUBLIC_TREE_BOUNDED_SLICE'), 'INVALID_OBSERVATION')
    for attempt in obs['attempts']:
        require(type(attempt) is dict and set(attempt) == {'capture_attempt_id','capture_status','deadline_elapsed_ms','tree_a_digest','tree_b_digest'}
                and _id(attempt['capture_attempt_id']) and identifier(attempt['capture_status'])
                and attempt['deadline_elapsed_ms'] == obs['deadline_elapsed_ms']
                and all(_sha(attempt[k], True) for k in ('tree_a_digest','tree_b_digest')), 'INVALID_OBSERVATION')
    require(len({a['capture_attempt_id'] for a in obs['attempts']}) == len(obs['attempts']), 'INVALID_OBSERVATION')
    _budget(obs['budget'], obs)
    if obs['capture_status'] in VALID:
        require(obs['started_elapsed_ms'] <= obs['ended_elapsed_ms'] < obs['deadline_elapsed_ms'], 'INVALID_OBSERVATION')
        require(all(identifier(obs[k]) for k in ('host_device_id', 'boot_session_id', 'observer_session_id')), 'INVALID_OBSERVATION')
        tree = obs['tree']
        fields = {'snapshot_id', 'root_readable', 'complete', 'nodes', 'root_local_id', 'truncated_reasons',
                  'known_scope', 'full_digest', 'execution_authority'}
        require(type(tree) is dict and set(tree) == fields and tree['execution_authority'] is False, 'INVALID_OBSERVATION')
        require(type(tree['nodes']) is list and 0 < len(tree['nodes']) <= 2048 and identifier(tree['snapshot_id']), 'INVALID_OBSERVATION')
        # Revalidate the serialized node contract; no handles/callbacks are restored.
        raw_nodes = []
        for node in tree['nodes']:
            require(type(node) is dict and 'children_local_ids' in node, 'INVALID_OBSERVATION')
            raw_nodes.append({k: v for k, v in node.items() if k != 'children_local_ids'})
        checked = copy_tree({'nodes': raw_nodes, 'complete': tree['complete'], 'root_readable': tree['root_readable'],
                             'truncated_reasons': tree['truncated_reasons']})
        require(checked['complete'] and checked['nodes'] == tree['nodes']
                and checked['full_digest'] == tree['full_digest']
                and checked['root_local_id'] == tree['root_local_id'], 'INVALID_OBSERVATION')
        last = obs['attempts'][-1]
        require(last['capture_status'] == obs['capture_status']
                and last['tree_a_digest'] == last['tree_b_digest'] == tree['full_digest'], 'INVALID_OBSERVATION')
        require(obs['window_before'] == obs['window_after'] and obs['window_after']['package'] == obs['environment']['app_package'],
                'INVALID_OBSERVATION')
        _metadata({'environment': obs['environment'], 'host_device_id': obs['host_device_id'],
                   'boot_session_id': obs['boot_session_id'], 'observer_session_id': obs['observer_session_id'], 'window':obs['window_after']})
        _navigation(obs['navigation_context']); _pair(obs['consistency'])
        expected = {'VALID_TREE_ONLY': ('TREE_A_B_CHECKED','NOT_EVALUATED'),
                    'PARTIAL_SCREENSHOT_FAILED': ('TREE_A_B_CHECKED','NOT_EVALUATED'),
                    'VALID_WINDOW_TIME_CHECKED': ('WINDOW_TIME_CHECKED','NOT_EVALUATED'),
                    'VALID_CONTENT_CHECKED_SIMULATED': ('CONTENT_CHECKED_SIMULATED','SIMULATED_NOT_MODEL')}
        require((obs['consistency']['pairing_status'], obs['consistency']['visual_content_check']) == expected[obs['capture_status']], 'INVALID_OBSERVATION')
        if obs['screenshot'] is not None: _screenshot(obs['screenshot'], obs)
        require((obs['capture_status'] == 'VALID_TREE_ONLY') == (obs['screenshot'] is None), 'INVALID_OBSERVATION')
        if obs['screenshot'] is not None:
            image = obs['screenshot']
            require((obs['capture_status'] == 'PARTIAL_SCREENSHOT_FAILED') == (image['status'] != 'AVAILABLE'), 'INVALID_OBSERVATION')
            require((obs['capture_status'] == 'VALID_CONTENT_CHECKED_SIMULATED') == (image['content_check'] is not None), 'INVALID_OBSERVATION')
    else:
        require(obs['tree'] is None and obs['screenshot'] is None, 'INVALID_OBSERVATION')
    return obs
