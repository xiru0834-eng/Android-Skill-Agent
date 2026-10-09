"""Offline re-score of the display matrix, checking order and independent input ledger."""
import argparse
import json
from pathlib import Path
from transfer_audit import evaluate
from transfer_requests import dispatched_requests
from workflow_experiment import write


def check_schedule(rows, blocks):
    expected = [(b['config'], c) for b in blocks for c in b['cases']]
    if len(rows) > len(expected): raise ValueError('Unexpected extra trials')
    for row, (config, case) in zip(rows, expected):
        if row['config'] != config or row['case'] != case: raise ValueError('Trial order or case changed')
    return len(expected)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    root = a.directory
    def load(path): return json.loads(path.read_text(encoding='utf-8'))
    protocol = load(root/'protocol.json')
    skill = load(root/'skill.json')
    recorded = load(root/'results.json')
    planned = check_schedule(recorded, protocol['blocks'])
    rows = []
    for index, entry in enumerate(recorded):
        folder = root/f'run-{index:03d}'
        if not entry.get('evidence_complete'):
            rows.append(dict(index=index, auditable=False))
            continue
        case, result, oracle, audits, journal = [load(folder/name) for name in
            ('case.json', 'terminal.json', 'oracle.json', 'audit.json', 'journal.json')]
        if any(case[k] != v for k, v in entry['case'].items()): raise ValueError('Reset case mismatch')
        if result['traceId'] != skill['traceId'] or result['traceSha256'] != skill['traceSha256']:
            raise ValueError('Wrong skill executed')
        score = evaluate(oracle, result, skill['finalGoals'], audits, case_id=case['caseId'], run_id=result['runId'])
        if any(entry[k] != v for k, v in score.items()): raise ValueError('Stored score mismatch')
        if any(j['seq'] != n+1 or j['runId'] != result['runId'] for n, j in enumerate(journal)):
            raise ValueError('Journal correlation failed')
        if journal[-1]['kind'] != 'RESULT' or journal[-1]['data']['status'] != result['status']:
            raise ValueError('Incomplete terminal journal')
        dispatched = dispatched_requests(journal, result['actions'])
        actual = [e for e in oracle['events'] if e['ms'] >= result['startedMs'] and e['kind'].startswith(('input:', 'edit:'))]
        rows.append(dict(index=index, auditable=True, confirmed=score['confirmed_success'],
            falseSuccess=score['false_success'], inputLedgerMatch=dispatched == [e['kind'].split(':', 1)[1] for e in actual],
            lateInputs=sum(e['ms'] > result['finishedMs'] for e in actual)))
    summary = dict(planned=planned, attempted=len(rows), complete=len(rows)==planned and all(r['auditable'] for r in rows),
        confirmed=sum(r.get('confirmed', False) for r in rows), falseSuccess=sum(r.get('falseSuccess', False) for r in rows),
        inputMismatch=sum(r.get('inputLedgerMatch') is False for r in rows), lateInputs=sum(r.get('lateInputs', 0) for r in rows))
    write(root/'reaudit.json', dict(summary=summary, rows=rows))
    print(json.dumps(summary))


if __name__ == '__main__': main()
