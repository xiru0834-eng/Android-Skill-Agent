"""Independent learning entrance; not registered as an Android action or normal user command."""
import argparse
import json
import os
from pathlib import Path

from draft_generator import Audit, Budget, DraftGenerator
from learning_request import RequestError, request_from_store
from model_api import ModelConfig, UploadGrant


def read_json(path, maximum=262144):
    with Path(path).open('rb') as f:
        raw = f.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('CLI_INPUT_LIMIT')
    return json.loads(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description='P3.1 draft-only learning. Never executes or publishes a Skill.')
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare', help='Read genuine P2 Store and persist public prompt, no network')
    for key in ('store', 'bundle', 'goal', 'audit-root'):
        prepare.add_argument('--' + key, required=True)
    prepare.add_argument('--expected-revision', type=int)
    generate = sub.add_parser('generate', help='Explicit paid learning only with current configuration, grant and budget')
    for key in ('request', 'config', 'grant', 'budget', 'audit-root'):
        generate.add_argument('--' + key, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            bundle = read_json(args.bundle, maximum=4194304)
            request = request_from_store(args.store, bundle['environment'], [bundle['bundle_id']], args.goal,
                                         expected_revision=args.expected_revision)
            out = DraftGenerator(args.audit_root, Budget()).run(request)
            code = 0 if out['status'] == 'MODEL_CONFIG_MISSING' else 2
        else:
            request = read_json(args.request)
            cfg = read_json(args.config)
            allowed_cfg = {'model', 'input_usd_per_million', 'output_usd_per_million', 'verified_rate_source'}
            if type(cfg) is not dict or set(cfg) != allowed_cfg:
                raise ValueError('CLI_CONFIGURATION_ERROR')
            budget = read_json(args.budget)
            if type(budget) is not dict or set(budget) != set(Budget.__dataclass_fields__):
                raise ValueError('CLI_CONFIGURATION_ERROR')
            grant = read_json(args.grant)
            if type(grant) is not dict or set(grant) != {'input_digest', 'environment'}:
                raise ValueError('CLI_CONFIGURATION_ERROR')
            # No credential file discovery; only explicit process key on this opted-in command.
            key = os.environ.get('OPENAI_API_KEY', '')
            config = ModelConfig(api_key=key, **cfg)
            out = DraftGenerator(args.audit_root, Budget(**budget)).run(request, config=config, grant=UploadGrant(**grant))
            code = 0 if out['status'] in ('DRAFT_ONLY', 'DRAFT_WITH_KNOWLEDGE_GAPS', 'KNOWLEDGE_GAP') else 2
    except (RequestError, ValueError, OSError, TypeError, KeyError):
        out = {'status': 'CLI_CONFIGURATION_ERROR', 'calls': 0, 'execution_authority': False,
               'ready_for_device_execution': False}
        try:
            audit = Audit(args.audit_root)
            out['audit_directory'] = str(audit.directory)
            audit.save('result.json', out)
        except OSError:
            out['status'] = 'AUDIT_STORAGE_ERROR'
        code = 2
    print(json.dumps({k: out.get(k) for k in ('status', 'calls', 'knowledge_gaps', 'audit_directory', 'execution_authority')}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
