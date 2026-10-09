"""Local definition/ledger CLI; contains no device or model client."""
import argparse
import json
from pathlib import Path

from learning_ledger import LearningLedger
from learning_scope import ReadinessContext, ScopeError, assess_scope, need, validate_scope
from source_audit import audit_file, historical_scope, load_catalog, receipt_for


def read_input(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(65537)
    need(len(raw) <= 65536, 'INPUT_LIMIT')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description='P2.1 offline contracts, not App learning execution')
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('validate', 'assess'):
        sub.add_parser(name).add_argument('scope')
    create = sub.add_parser('create')
    create.add_argument('scope')
    create.add_argument('database')
    append = sub.add_parser('append')
    append.add_argument('database')
    append.add_argument('event')
    append.add_argument('--revision', required=True, type=int)
    sub.add_parser('inspect').add_argument('database')
    sub.add_parser('audit-sources')
    sample = sub.add_parser('historical-sample')
    sample.add_argument('--database', help='Explicit NEW local ledger path; never overwrites')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'validate':
            result = {'result': 'VALID_CONTRACT', 'scope': validate_scope(read_input(args.scope)), 'execution_authority': False}
        elif args.operation == 'assess':
            result = assess_scope(read_input(args.scope))
        elif args.operation == 'create':
            result = LearningLedger.create(args.database, read_input(args.scope)).inspect()
        elif args.operation == 'append':
            store = LearningLedger.open(args.database)
            revision = store.append(read_input(args.event), expected_revision=args.revision)
            result = {'result': 'RECORDED', 'revision': revision, 'execution_authority': False}
        elif args.operation == 'inspect':
            result = LearningLedger.open(args.database).inspect()
        else:
            audits = [audit_file(spec) for spec in load_catalog()]
            if args.operation == 'audit-sources':
                result = {'audits': audits, 'channel': 'REAL_LOCAL_HISTORICAL_FILES',
                          'model_calls': 0, 'device_actions': 0, 'execution_authority': False}
            else:
                audit = audits[0]
                scope = historical_scope(audit)
                context = ReadinessContext(materials=(receipt_for(audit),))
                result = {'scope': scope, 'assessment': assess_scope(scope, context), 'execution_authority': False}
                if args.database:
                    store = LearningLedger.create(args.database, scope)
                    source_id = audit['source']['source_id']
                    store.append({'kind': 'HUMAN_COST', 'event_id': 'cost.historical_demo',
                                  'activity_id': audit['trace_id'], 'source_ids': [source_id],
                                  'category': 'DEMONSTRATION', 'actor': 'AUTOMATED', 'amount': 1,
                                  'unit': 'count', 'evidence_refs': [audit['source']['evidence_ref']],
                                  'supersedes_event_id': None}, expected_revision=0)
                    store.append({'kind': 'HUMAN_COST', 'event_id': 'cost.unknown_preconfig',
                                  'activity_id': 'historical_preconfiguration', 'source_ids': [source_id],
                                  'category': 'PRECONFIGURATION', 'actor': 'UNKNOWN', 'amount': None,
                                  'unit': 'ms', 'evidence_refs': [audit['source']['evidence_ref']],
                                  'supersedes_event_id': None}, expected_revision=1)
                    result['ledger'] = store.inspect()
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))
        return 2 if result.get('status') == 'BLOCKED' else 0
    except ScopeError as error:
        print(json.dumps({'result': 'REJECTED', 'code': error.code, 'execution_authority': False}))
        return 1
    except OSError:
        print(json.dumps({'result': 'REJECTED', 'code': 'LOCAL_IO_ERROR', 'execution_authority': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
