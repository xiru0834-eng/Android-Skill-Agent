"""Validate bounded timing evidence; never authorize device inputs."""


def check_profile(result,journal):
    prefix=result['profilePrefix'];parts=('SNAPSHOT','TARGET_LOOKUP','INPUT','JOURNAL')
    if prefix.get('scope')!='before this RESULT journal and result-file writes; non-overlapping measured sections only':
        raise ValueError('PROFILE_SCOPE')
    for part in parts:
        v=prefix[part]
        if any(type(v[k]) is not int or v[k]<0 for k in ('count','totalMs','maxMs')):
            raise ValueError('PROFILE_COUNTER')
        if v['maxMs']>v['totalMs'] or v['totalMs']>v['count']*v['maxMs']:
            raise ValueError('PROFILE_RANGE')
    if prefix['INPUT']['count']!=len(result['actions']):raise ValueError('PROFILE_INPUT_COUNT')
    if not journal or journal[-1]['kind']!='RESULT' or prefix['JOURNAL']['count']!=len(journal)-1:
        raise ValueError('PROFILE_JOURNAL_PREFIX')
    if prefix['SNAPSHOT']['count']<sum(j['kind']=='OBSERVATION' for j in journal):
        raise ValueError('PROFILE_OBSERVATION_COUNT')
    measured=sum(prefix[p]['totalMs'] for p in parts)
    elapsed=result['finishedMs']-result['startedMs']
    if measured>elapsed:raise ValueError('PROFILE_OVERLAP_OR_CLOCK')
    return dict(measuredMs=measured,unattributedMs=elapsed-measured,parts={p:dict(prefix[p]) for p in parts},
                scope=prefix['scope'])
