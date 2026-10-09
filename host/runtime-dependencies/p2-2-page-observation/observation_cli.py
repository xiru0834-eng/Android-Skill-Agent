"""Explicit offline fixture demonstration and local memory read commands only."""
import argparse
import json
from pathlib import Path

from observation_tree import ObservationError, SECRET, require
from p22deps import LearningBudget, ScopeAuthorization, ScopeError, scope_digest


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2))


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default repeats invalid input, which may contain a pasted key.
        emit({'status':'REJECTED','code':'INVALID_CLI_REQUEST','execution_authority':False})
        raise SystemExit(2)


def integer(value, low, high):
    try: parsed = int(value)
    except (ValueError, TypeError): raise ObservationError('INVALID_CLI_REQUEST') from None
    require(low <= parsed <= high, 'INVALID_CLI_REQUEST')
    return parsed


def main(argv=None):
    parser = QuietParser()
    parser.add_argument('command', choices=['fixture-capture','inspect','search','capture-android'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--id')
    parser.add_argument('--value', default='20')
    parser.add_argument('--entity', default='Room 101')
    parser.add_argument('--role', default='slider')
    parser.add_argument('--limit', default='100')
    args = parser.parse_args(argv)
    if args.command == 'capture-android':
        emit({'status':'BLOCKED','code':'NATIVE_PIPELINE_NOT_WIRED','execution_authority':False,
              'device_actions':0,'model_calls':0})
        return 2
    store = None
    try:
        from observation_store import ObservationStore
        if args.command == 'fixture-capture':
            value = integer(args.value, 0, 100)
            require(type(args.entity) is str and 0 < len(args.entity) <= 256 and not SECRET.search(args.entity), 'INVALID_CLI_REQUEST')
            # This command deliberately imports synthetic test support, never a device adapter.
            from test_support import Clock, FixturePort, scope_fixture, frame_fixture
            from observation_capture import ObservationCollector
            from observation_identity import derive_page
            clock = Clock(); scope = scope_fixture(); frame = frame_fixture(value=value, entity=args.entity)
            budget = LearningBudget(scope, clock=clock)
            port = FixturePort([frame,frame], None, clock)
            collector = ObservationCollector(scope, port, clock=clock, budget=budget,
                authorization=ScopeAuthorization(scope_digest(scope),'env.room','fixture.host',6000,observe=True))
            obs = collector.observe()
            store = ObservationStore(Path(args.db), create=True)
            saved = store.append(obs, entity_types=scope['task']['entity_types'], budget=budget)
            emit({'status':'OFFLINE_FIXTURE_SAVED', 'channel':'OFFLINE_CALLBACK_SIMULATION', 'saved':saved,
                  'observation':obs, 'page':derive_page(obs,entity_types=scope['task']['entity_types']),
                  'tree_reads':port.tree_reads, 'device_actions':0, 'model_calls':0, 'execution_authority':False})
        else:
            require(args.id is not None, 'INVALID_CLI_REQUEST')
            limit = integer(args.limit, 1, 100)
            store = ObservationStore(Path(args.db))
            emit(store.inspect_observation(args.id) if args.command == 'inspect' else
                 store.search_in_observation(args.id, role=args.role, limit=limit))
        return 0
    except (ObservationError, ScopeError) as error:
        code = str(error)
        require(code.replace('_','').isalnum() and not SECRET.search(code), 'INTERNAL_ERROR')
        emit({'status':'REJECTED','code':code,'execution_authority':False})
        return 2
    except (OSError, ValueError, TypeError):
        emit({'status':'REJECTED','code':'LOCAL_IO_ERROR','execution_authority':False})
        return 2
    finally:
        if store is not None: store.close()


if __name__ == '__main__': raise SystemExit(main())
