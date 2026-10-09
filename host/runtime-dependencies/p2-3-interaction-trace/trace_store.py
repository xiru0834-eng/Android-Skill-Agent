"""Append-only evidence storage. Loading never creates sessions, input permits, or live Nodes."""
import json
from pathlib import Path
import sqlite3
import threading

from p23deps import canonical, digest, scope_digest, validate_scope, identifier, derive_page
from trace_contract import (TraceError, need, detached, observation, validate_interaction, CHANNEL, SOURCES, MAX_STEPS)
from navigation_graph import NavigationGraph
from safe_navigation import SafetyPolicy
from interaction_trace import MAX_BUNDLE_BYTES

FIELDS = {'kind','schema_version','trace_id','channel','state','scope','scope_hash','budget','safety_policy',
          'observations','interactions','navigation_attempts','diagnostics','source_counts','map',
          'execution_authority','native_integration','evidence_level','forensic_tail_bytes'}
ATTEMPT_FIELDS = {'kind','schema_version','attempt_id','channel','status','planning_observation_id',
                  'before_observation_id','after_observation_id','interaction_id','post_observations',
                  'failure_code','execution_authority','model_calls'}


def validate_bundle(value):
    try:
        return _validate_bundle(value)
    except TraceError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise TraceError('INVALID_BUNDLE') from error


def _validate_bundle(value):
    b = detached(value)
    need(type(b) is dict and set(b) == FIELDS and b['kind']=='TraceBundle' and b['schema_version']=='1.0'
         and identifier(b['trace_id']) and b['channel']==CHANNEL and b['execution_authority'] is False
         and b['native_integration']=='BLOCKED' and b['evidence_level']=='NOT_REAL_ANDROID_EVIDENCE',
         'INVALID_BUNDLE')
    need(len(canonical(b).encode('utf-8'))<=MAX_BUNDLE_BYTES, 'BUNDLE_SIZE_LIMIT')
    need(type(b['forensic_tail_bytes']) is int and 0<=b['forensic_tail_bytes']<=MAX_BUNDLE_BYTES,
         'INVALID_BUDGET')
    scope=validate_scope(b['scope'])
    need(scope_digest(scope)==b['scope_hash'], 'SCOPE_CHANGED')
    stack=[b]
    while stack:
        item=stack.pop()
        if type(item) is dict:
            need('execution_authority' not in item or item['execution_authority'] is False, 'AUTHORITY_IN_EVIDENCE')
            stack.extend(item.values())
        elif type(item) is list:
            stack.extend(item)
    need(type(b['observations']) is list and len(b['observations'])<=4096
         and type(b['interactions']) is list and len(b['interactions'])<=MAX_STEPS,
         'INVALID_BUNDLE')
    obs={}
    for raw in b['observations']:
        o=observation(raw)
        need(o['observation_id'] not in obs, 'DUPLICATE_OBSERVATION')
        need(o['scope_hash']==b['scope_hash'] and o['environment']==scope['target']
             and o['budget']['session_id']==b['budget']['session_id'], 'OBSERVATION_CONTEXT_CHANGED')
        obs[o['observation_id']]=o
    graph=NavigationGraph(scope['task']['entity_types'])
    steps={};dispatches=set()
    for step in b['interactions']:
        try:
            pre=obs[step['before']['observation_id']]
            post=obs[step['after']['observation_id']] if step['after'] is not None else None
            checked=validate_interaction(step,pre,post,scope['task']['entity_types'])
        except (KeyError,TypeError) as error:
            from trace_contract import TraceError
            raise TraceError('BROKEN_OBSERVATION_REFERENCE') from error
        need(checked['interaction_id'] not in steps and checked['dispatch']['dispatch_id'] not in dispatches,
             'DUPLICATE_INTERACTION_OR_DISPATCH')
        steps[checked['interaction_id']]=checked
        dispatches.add(checked['dispatch']['dispatch_id'])
        graph.add_interaction(checked,pre,post)
    need(b['source_counts']=={s:sum(v['source']==s for v in steps.values()) for s in SOURCES},
         'SOURCE_COUNT_MISMATCH')
    policy=SafetyPolicy(b['safety_policy']['rules'])
    need(policy.snapshot()==b['safety_policy'], 'SAFETY_POLICY_MISMATCH')
    actual=b['map']; expected={e['edge_id']:e for e in graph.snapshot()['edges']}
    need(type(actual) is dict and set(actual)==set(graph.snapshot()) and actual['real_verified_edges']==0,
         'INVALID_MAP')
    need(type(actual['edges']) is list and len(actual['edges'])<=128, 'INVALID_MAP')
    for edge in actual['edges']:
        if edge.get('status')=='HYPOTHESIS':
            try:
                source=derive_page(obs[edge['source_page']['observation_id']],entity_types=scope['task']['entity_types'])
                need(source==edge['source_page'], 'HYPOTHESIS_SOURCE_MISMATCH')
                proposed=graph.add_hypothesis(source,edge['arrival_condition'],edge['evidence']['model_ref'])
                need(proposed==edge and edge['edge_id'] not in expected, 'HYPOTHESIS_EVIDENCE_MISMATCH')
                expected[edge['edge_id']]=proposed
            except (KeyError,TypeError) as error:
                from trace_contract import TraceError
                raise TraceError('HYPOTHESIS_EVIDENCE_MISMATCH') from error
    need(len(actual['edges'])==len(expected), 'MAP_EVIDENCE_MISMATCH')
    edge_ids=set()
    for edge in actual['edges']:
        need(edge['edge_id'] in expected and edge['edge_id'] not in edge_ids, 'MAP_EVIDENCE_MISMATCH')
        edge_ids.add(edge['edge_id']); projected=expected[edge['edge_id']]
        if edge['status']=='INVALIDATED':
            need(edge['history'][:1]==projected['history'] and len(edge['history'])>1
                 and all(type(v) is dict and set(v)=={'status','reason'} and v['status']=='INVALIDATED'
                         and identifier(v['reason']) for v in edge['history'][1:]), 'INVALID_MAP_HISTORY')
            projected=dict(projected,status='INVALIDATED',history=edge['history'])
        need(edge==projected, 'MAP_EVIDENCE_MISMATCH')
    need(actual['verified_simulated_edges']==sum(e['status']=='VERIFIED_SIMULATED' for e in actual['edges']),
         'MAP_COUNT_MISMATCH')
    need(type(actual['memory_revision']) is int
         and actual['memory_revision']==len(expected)+sum(len(e['history'])-1 for e in actual['edges']),
         'MAP_REVISION_MISMATCH')
    need(type(b['navigation_attempts']) is list and len(b['navigation_attempts'])<=4096, 'INVALID_ATTEMPTS')
    attempts=set()
    for a in b['navigation_attempts']:
        need(type(a) is dict and set(a)==ATTEMPT_FIELDS and a['kind']=='NavigationAttempt'
             and a['schema_version']=='1.0' and a['channel']==CHANNEL and identifier(a['attempt_id'])
             and a['attempt_id'] not in attempts and identifier(a['status']) and a['execution_authority'] is False
             and type(a['post_observations']) is int and 0<=a['post_observations']<=4
             and type(a['model_calls']) is int and 0<=a['model_calls']<=1
             and identifier(a['failure_code'],nullable=True), 'INVALID_ATTEMPTS')
        attempts.add(a['attempt_id'])
        for key in ('planning_observation_id','before_observation_id','after_observation_id'):
            need(a[key] is None or a[key] in obs, 'BROKEN_OBSERVATION_REFERENCE')
        need(a['interaction_id'] is None or a['interaction_id'] in steps, 'BROKEN_INTERACTION_REFERENCE')
        if a['status']=='ARRIVAL_VERIFIED_SIMULATED':
            need(a['interaction_id'] is not None and steps[a['interaction_id']]['status']==a['status'],
                 'FALSE_VERIFIED_ATTEMPT')
    need(type(b['diagnostics']) is list and len(b['diagnostics'])<=4096, 'INVALID_DIAGNOSTICS')
    # Stored budget is historical accounting, never permission and never used to resume.
    need(type(b['budget']) is dict and b['budget'].get('execution_authority') is False
         and b['budget'].get('scope_hash')==b['scope_hash'], 'INVALID_BUDGET')
    return b


class TraceStore:
    def __init__(self, path, *, max_bytes=16777216, read_only=False):
        need(type(max_bytes) is int and 1<=max_bytes<=67108864, 'INVALID_STORE_LIMIT')
        self.max_bytes=max_bytes
        need(type(read_only) is bool, 'INVALID_STORE_MODE')
        self.read_only=read_only
        need(type(path) in (str,Path) or isinstance(path,Path), 'INVALID_STORE_PATH')
        self.path=Path(path)
        need(self.path.suffix=='.sqlite' and self.path.is_absolute() and self.path.parent.is_dir(),
             'INVALID_STORE_PATH')
        self._lock=threading.RLock()
        self.con=None
        try:
            existed=self.path.exists()
            need(not read_only or existed, 'STORE_NOT_FOUND')
            connection=('file:'+self.path.as_posix()+'?mode=ro') if read_only else self.path
            self.con=sqlite3.connect(connection,uri=read_only,timeout=2,isolation_level=None,check_same_thread=False)
            tables={r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existed:
                need(tables=={'metadata','traces'}, 'FOREIGN_OR_INCOMPATIBLE_STORE')
                metadata=self.con.execute('SELECT version,revision FROM metadata').fetchall()
                need(len(metadata)==1 and metadata[0][0]=='p23.1' and type(metadata[0][1]) is int,
                     'STORE_SCHEMA_INCOMPATIBLE')
            else:
                self.con.execute('BEGIN IMMEDIATE')
                self.con.execute('CREATE TABLE metadata(version TEXT NOT NULL, revision INTEGER NOT NULL)')
                self.con.execute("INSERT INTO metadata VALUES('p23.1',0)")
                self.con.execute('CREATE TABLE traces(revision INTEGER PRIMARY KEY, trace_id TEXT UNIQUE NOT NULL, '
                                 'payload TEXT NOT NULL, digest TEXT NOT NULL, previous TEXT NOT NULL, chain TEXT NOT NULL)')
                self.con.execute('COMMIT')
        except Exception:
            if self.con is not None:self.con.close()
            raise

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):self.con.close()

    def revision(self):
        return self.con.execute('SELECT revision FROM metadata').fetchone()[0]

    def _rows(self):
        total=self.con.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM traces').fetchone()[0]
        need(total<=self.max_bytes, 'STORE_SIZE_LIMIT')
        rows=self.con.execute('SELECT revision,trace_id,payload,digest,previous,chain FROM traces ORDER BY revision').fetchall()
        previous='0'*64
        values=[]
        for n,row in enumerate(rows,1):
            rev,tid,payload,sha,prev,chain=row
            need(rev==n and prev==previous, 'STORE_CHAIN_ERROR')
            try: b=validate_bundle(json.loads(payload))
            except (ValueError,TypeError) as error:
                from trace_contract import TraceError
                raise TraceError('STORE_CORRUPT') from error
            need(digest(b)==sha and tid==b['trace_id'] and digest({'revision':rev,'trace_id':tid,'digest':sha,'previous':prev})==chain,
                 'STORE_DIGEST_ERROR')
            previous=chain;values.append((rev,b,sha,chain))
        need(self.revision()==len(rows), 'STORE_REVISION_ERROR')
        return values

    def append(self,value,*,expected_revision,fail_before_commit=False):
        need(not self.read_only, 'STORE_READ_ONLY')
        b=validate_bundle(value)
        need(type(expected_revision) is int and expected_revision>=0
             and type(fail_before_commit) is bool, 'INVALID_REVISION')
        with self._lock:
            self.con.execute('BEGIN IMMEDIATE')
            try:
                rows=self._rows()
                need(sum(len(canonical(row[1]).encode('utf-8')) for row in rows)
                     + len(canonical(b).encode('utf-8'))<=self.max_bytes, 'STORE_SIZE_LIMIT')
                need(self.revision()==expected_revision, 'MEMORY_REVISION_CONFLICT')
                need(all(row[1]['trace_id']!=b['trace_id'] for row in rows), 'DUPLICATE_TRACE')
                rev=expected_revision+1;prev=rows[-1][3] if rows else '0'*64;sha=digest(b)
                chain=digest({'revision':rev,'trace_id':b['trace_id'],'digest':sha,'previous':prev})
                self.con.execute('INSERT INTO traces VALUES(?,?,?,?,?,?)',(rev,b['trace_id'],canonical(b),sha,prev,chain))
                self.con.execute('UPDATE metadata SET revision=?',(rev,))
                need(not fail_before_commit,'SIMULATED_STORAGE_INTERRUPTION')
                self.con.execute('COMMIT')
                return {'revision':rev,'trace_id':b['trace_id'],'sha256':sha,'execution_authority':False}
            except Exception:
                self.con.execute('ROLLBACK')
                raise

    def read(self,trace_id):
        need(identifier(trace_id) and all(c.isalnum() or c in '_.:-' for c in trace_id), 'INVALID_TRACE_ID')
        with self._lock:
            self.con.execute('BEGIN')
            try:
                for rev,b,sha,chain in self._rows():
                    if b['trace_id']==trace_id:
                        return {'status':'FOUND','bundle':b,'revision':rev,'sha256':sha,
                                'execution_authority':False,'restore_mode':'EVIDENCE_ONLY_NO_SESSION_RESUME'}
            finally:
                self.con.execute('ROLLBACK')
        return {'status':'NOT_FOUND','execution_authority':False}

    def list_traces(self,*,limit=20):
        need(type(limit) is int and 1<=limit<=100,'INVALID_LIMIT')
        with self._lock:
            self.con.execute('BEGIN')
            try:
                rows=self._rows()
                return {'items':[{'trace_id':b['trace_id'],'revision':rev,'sha256':sha} for rev,b,sha,chain in rows[:limit]],
                        'total':len(rows),'revision':self.revision(),'execution_authority':False,
                        'is_live_ui_query':False}
            finally:
                self.con.execute('ROLLBACK')
