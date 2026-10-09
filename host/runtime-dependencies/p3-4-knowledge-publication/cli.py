"""Read-only/repository-archive CLI. No publish, model, ADB or execute command."""
import argparse
from p34deps import canonical, digest
from knowledge import KnowledgeLibrary, KnowledgeError
from material_package import archive_material, read_archive


def main():
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--p31-audit'); operation.add_argument('--read-archive'); operation.add_argument('--read-key')
    parser.add_argument('--bundle', action='append', default=[]); parser.add_argument('--output-root')
    parser.add_argument('--library-root'); parser.add_argument('--source-root', action='append', required=True)
    args = parser.parse_args()
    if args.p31_audit:
        if not args.bundle or not args.output_root: parser.error('--bundle and --output-root required')
        directory = archive_material(args.p31_audit, args.bundle, args.output_root, approved_roots=args.source_root)
        value = read_archive(directory, approved_roots=args.source_root)
        print(canonical({'status': value['status'], 'archive': str(directory), 'execution_authority': False}))
    elif args.read_archive:
        value = read_archive(args.read_archive, approved_roots=args.source_root)
        print(canonical({'readback': 'PASS', 'status': value['status'], 'archive_digest': digest(value),
                         'formal_retrievable': False, 'execution_authority': False, 'human_cost': value['human_cost'],
                         'actual_points': len(value['actual_points']), 'model_cost': value['model_cost']}))
    else:
        if not args.library_root: parser.error('--library-root required')
        library = KnowledgeLibrary.open(args.library_root, approved_roots=args.source_root)
        try: print(canonical(library.inspect(args.read_key)))
        finally: library.close()
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (KnowledgeError, OSError, ValueError) as error:
        # Do not echo original untrusted text or credentials on a malformed file.
        print(canonical({'status': 'ARCHIVE_ERROR', 'code': getattr(error, 'code', type(error).__name__), 'execution_authority': False}))
        raise SystemExit(1)
