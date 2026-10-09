"""Independent closeout accounting. No Android or model capabilities."""
import hashlib

def verified_file_digest(data,expected_size):
    if len(data)!=expected_size or classify_backup(data)['status']!='PRESENT':
        raise ValueError('BINARY_FILE_READ_UNCONFIRMED')
    return classify_backup(data)


def classify_backup(data):
    if data.startswith(b'cat: ') and b'No such file or directory' in data:
        return {'status':'NOT_PRESENT','reason':'OLD_EXEC_OUT_MISSING_FILE_ERROR_WAS_NOT_DATA'}
    return {'status':'PRESENT','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}


def compare_protection(before,after):
    issues=[]
    for name,expected in before.items():
        observed=after.get(name,{})
        if expected.get('status')!=observed.get('status') or expected.get('status')=='PRESENT' and expected.get('sha256')!=observed.get('sha256'):
            issues.append(name)
    return {'verdict':'FAIL' if issues else 'PASS','checked':len(before),'drift':issues,
            'present_files':sum(v.get('status')=='PRESENT' for v in before.values())}


def score_flow(summary,audit):
    correct=(summary.get('status')=='PASS' and summary.get('observations')==5
        and summary.get('real_navigation_actions')==4 and summary.get('interactions_verified')==4
        and audit.get('write_count')==0 and audit.get('pending_count')==0 and audit.get('state_unchanged') is True)
    return {'correct':correct,'reported_success':summary.get('status')=='PASS',
            'false_success':summary.get('status')=='PASS' and not correct}


def assert_readonly_proof(proof):
    if proof.get('native_counters_unchanged') is not True or proof.get('business_ledger_unchanged') is not True or proof.get('query_calls')!=4:
        raise ValueError('READONLY_EVIDENCE_INCOMPLETE')
    return True
