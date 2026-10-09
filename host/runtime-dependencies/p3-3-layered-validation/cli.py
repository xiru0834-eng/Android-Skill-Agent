"""Read-only host audit CLI. There is no execute/publish/model/device option."""
import argparse
from material_io import inspect_material, save_report, read_saved
from p33deps import canonical


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--p31-audit'); group.add_argument('--read-saved')
    parser.add_argument('--bundle', action='append')
    parser.add_argument('--package'); parser.add_argument('--task'); parser.add_argument('--output-root')
    args = parser.parse_args()
    if args.read_saved:
        if any((args.bundle, args.package, args.task, args.output_root)): parser.error('read-saved accepts no mutation options')
        report = read_saved(args.read_saved)
        print(canonical({'status': report['status'], 'execution_authority': False, 'readback': 'PASS'}))
    else:
        if not args.bundle or not args.output_root: parser.error('explicit bundles and new output-root required')
        report = inspect_material(args.p31_audit, args.bundle, package_path=args.package, task_path=args.task)
        directory = save_report(args.output_root, report)
        print(canonical({'status': report['status'], 'output_directory': str(directory), 'execution_authority': False}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
