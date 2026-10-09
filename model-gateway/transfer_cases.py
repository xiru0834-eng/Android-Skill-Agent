"""Predeclared balanced execution cases; repetitions are not independent skills."""
import random

INITIALS=[[0,40,0,3],[1,60,0,3],[0,40,1,1],[1,40,1,3],[0,60,0,1],[1,60,1,1]]

def make_cases(suite,repeats):
    if suite not in ('normal','challenge') or not 1<=repeats<=20:raise ValueError('CASE_PARAMETERS')
    rows=[];rng=random.Random(91284)
    for repeat in range(repeats):
        if suite=='normal':
            block=[dict(initial=list(v),initialId='S'+str(i),fault='normal',condition='S'+str(i),repeat=repeat) for i,v in enumerate(INITIALS)]
        else:
            block=[dict(initial=list(INITIALS[0]),initialId='S0',fault=f,condition=f,repeat=repeat)
                   for f in ('delay','navdelay','drop','rollback','missing','duplicate','dirty')]
            block.append(dict(initial=list(INITIALS[5]),initialId='S5',fault='dirty',condition='dirty-already-at-target',repeat=repeat))
        rng.shuffle(block);rows.extend(block)
    return rows
