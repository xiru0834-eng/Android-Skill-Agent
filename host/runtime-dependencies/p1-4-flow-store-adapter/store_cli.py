"""Operator-only knowledge CLI. No phone/model/permission/publish switches.

The demo is a explicitly handwritten simulation and publishes only in the
isolated SIMULATION_ONLY namespace. Production knowledge is never auto-run.
"""
import argparse
import json
from pathlib import Path
import sys
from p14deps import fixture_bundle, canonical, compiler
from flow_store import FlowStore, StoreError


def demo(root):
    from flow_adapter import FlowAdapter
    from records import ValidationAuthority, PublishAuthority
    from test_support import Clock, RoomPort, policy_for
    store = FlowStore.create(root)
    flow, package, task = fixture_bundle()
    lifecycle = []
    try:
        row = store.save_draft(canonical(flow), package, 0)
        key = row['key']; lifecycle.append(row['state'])
        row = store.check(key, 1, task, None); lifecycle.append(row['state'])
        plan = compiler.compile_flow(flow, package, task, None)
        policy, clock = policy_for(plan), Clock()
        adapter, port = FlowAdapter(enabled=True, clock=clock), RoomPort(clock)
        result = adapter.validate_candidate(store, key, task, ValidationAuthority(key, 'operator.test_fixture', True),
                                            lambda: policy, port)
        if result.evidence is None:
            raise StoreError('DEMO_VALIDATION_FAILED')
        row = store.record_validation(key, 2, result.evidence); lifecycle.append(row['state'])
        row = store.publish(key, 3, PublishAuthority(key, 'operator.test_fixture', policy.environment_hash, 'LOGIC_SIMULATION', True))
        lifecycle.append(row['state'])
    finally:
        store.close()
    store = FlowStore.open(root)
    try:
        loaded = store.load(key)
        return {'kind': 'TEST_FIXTURE_DEMO', 'lifecycle': lifecycle, 'evidence_channel': 'LOGIC_SIMULATION',
                'model_calls': 0, 'device_actions': 0, 'simulation_dispatch_count': result.receipt['dispatch_count'],
                'run_receipt': result.receipt, 'validated_scope': loaded['scopes'][0],
                'reloaded': {'key': key, 'state': loaded['state'], 'sha256': loaded['sha256'],
                             'execution_authority': loaded['execution_authority'], 'resume_authority': loaded['resume_authority'],
                             'device_execution_verified': loaded['device_execution_verified']}}
    finally:
        store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='P1.4 local knowledge only; no device or model operations')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'demo', 'inspect', 'export'):
        command = commands.add_parser(name)
        command.add_argument('--root', required=True, help='Trusted operator chosen isolated storage directory')
        if name in ('inspect', 'export'):
            command.add_argument('--key', required=True, help='Exact immutable Flow ID@version, not a filesystem path')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            result = demo(args.root)
        elif args.command == 'init':
            store = FlowStore.create(args.root)
            store.close()
            result = {'status': 'STORE_CREATED', 'mode': 'SIMULATION_ONLY', 'execution_authority': False}
        else:
            store = FlowStore.open(args.root)
            try:
                result = store.load(args.key) if args.command == 'inspect' else store.export_knowledge(args.key)
            finally:
                store.close()
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except StoreError as error:
        print(json.dumps({'status': 'REJECTED', 'code': error.code, 'execution_authority': False}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
