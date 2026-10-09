"""Local compiler CLI. Reads three explicit files; never executes a plan."""
import argparse
import json
import sys

_dependency_error = False
try:
    from dependencies import contracts as old, verify_dependencies
    from compiler import compile_flow, CompileError, checked
except (OSError, ValueError):
    _dependency_error = True


def load_document(path, field):
    return checked(lambda: old._load(path), field, 'FORMAT')


def main(argv=None):
    parser = argparse.ArgumentParser(description='P1.3 offline compile only. No device input authority.')
    for name in ('flow', 'package', 'task'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        if _dependency_error:
            raise ValueError('DEPENDENCY_UNAVAILABLE')
        verify_dependencies()
    except (OSError, ValueError):
        print(json.dumps(dict(status='REJECTED', code='DEPENDENCY_UNAVAILABLE', path='$.dependencies',
                              layer='CAPABILITY', execution_authority=False, ready_for_device_execution=False)))
        return 2
    try:
        values = [load_document(getattr(args, name), '$.' + name) for name in ('flow', 'package', 'task')]
        result = compile_flow(*values, None).to_dict()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except CompileError as error:
        print(json.dumps(error.receipt(), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
