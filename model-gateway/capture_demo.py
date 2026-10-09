"""Opt-in controlled phone capture, using existing UI paths. No cloud or approval writes."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'evaluation/trace-evidence'))
import device_suite as device
from qualify import approvals
from contracts import validate_trace


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-phone-test', action='store_true')
    args = p.parse_args()
    if not args.allow_phone_test: raise SystemExit('Explicit phone test flag required')
    args.output.mkdir(parents=True, exist_ok=False)
    save = lambda name, value: device.s.save(args.output/name, value)
    before = approvals(); save('approvals-before.json', before)
    save('previous-evidence.json', device.trace())
    started = False
    try:
        device.main_screen(); device.s.click('selectBench')
        if 'Service ON' not in device.s.find(resource=device.s.PROBE+':id/status').get('text', ''):
            raise RuntimeError('Enable accessibility service manually first')
        started = True
        device.begin()
        trace = device.finish(); save('trace.json', trace)
        validate_trace(trace)
        after = approvals(); save('approvals-after.json', after)
        if before != after: raise RuntimeError('Existing approvals changed')
        save('result.json', dict(status='CAPTURED', source=trace['source'], approvalsPreserved=True,
                                 oracle=device.oracle(), modelCalls=0))
        print('CAPTURED: stopped ADB_TEST evidence; existing approvals unchanged')
    except Exception as error:
        save('failure.json', dict(errorType=type(error).__name__, reason=str(error)))
        raise
    finally:
        if started:
            device.evidence_screen(); device.s.click('traceStop')


if __name__ == '__main__': main()
