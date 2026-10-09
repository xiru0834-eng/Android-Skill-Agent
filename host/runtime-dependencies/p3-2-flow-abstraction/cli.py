"""P3.2 read-only source analysis. This CLI does not provide execution or model options."""
import argparse
import json
from audit_io import inspect_original, save_report


def main():
    parser = argparse.ArgumentParser(description='Analyze an original P3.1 receipt without executing a Flow')
    parser.add_argument('--p31-audit', required=True)
    parser.add_argument('--bundle', required=True, action='append')
    parser.add_argument('--output-root', required=True)
    args = parser.parse_args()
    result = inspect_original(args.p31_audit, args.bundle)
    try:
        directory = save_report(args.output_root, result)
    except (OSError, ValueError, TypeError):
        print(json.dumps({'status': 'AUDIT_STORAGE_ERROR', 'execution_authority': False}))
        return 1
    print(json.dumps({'status': result['status'], 'audit_directory': str(directory), 'execution_authority': False}))
    return 0 if result['status'] in ('PARAMETERIZED_DRAFT', 'PARAMETERIZED_DRAFT_UNCHANGED', 'BLOCKED_NO_CANDIDATE', 'PARAMETER_EVIDENCE_UNAVAILABLE') else 1


if __name__ == '__main__': raise SystemExit(main())
