"""One factor at a time; synthetic faults are labelled, not real device events."""
import copy,random
from bidirectional_cases import primary,call

CONFIGS=[
    dict(name='normal',factor='baseline'),
    dict(name='resolution-low',factor='size',value='480x854'),
    dict(name='resolution-high',factor='size',value='1080x1920'),
    dict(name='density-low',factor='density',value='160'),
    dict(name='density-high',factor='density',value='320'),
    dict(name='font-13',factor='font',value='1.3'),
    dict(name='font-15',factor='font',value='1.5'),
    dict(name='initial-all-on',factor='initial'),
    dict(name='observation-delay',factor='injection',arguments=dict(read_delay_ms=150)),
    dict(name='stale-before',factor='injection',arguments=dict(source_fault='STALE_TREE',fault_count=1,fault_at=1)),
    dict(name='stale-after-input',factor='injection',arguments=dict(source_fault='STALE_TREE',fault_count=1,fault_at=4)),
    dict(name='loading-once',factor='injection',arguments=dict(source_fault='PAGE_LOADING',fault_count=1,fault_at=1)),
]

def valid_cases(config,repeats=3):
    rows=[]
    for rep in range(repeats):
        block=copy.deepcopy(primary());random.Random(74123+rep).shuffle(block)
        for row in block:
            row['case_id']+=f'-{config["name"]}-r{rep}';row['repeat']=rep
            if config['factor']=='initial':row['initial']=[1,100,1,30]
        rows.extend(block)
    return rows

def safety_cases(repeats=3):
    specs=[
        ('null-root','ENVIRONMENT_ERROR',dict(source_fault='NO_TREE',fault_count=1)),
        ('read-error','ENVIRONMENT_ERROR',dict(source_fault='ROOT_READ_FAILED',fault_count=1)),
        ('overlay-before','BLOCKED_BY_OVERLAY',dict(source_fault='BLOCKED_BY_OVERLAY',fault_count=1)),
        ('overlay-after','BLOCKED_BY_OVERLAY',dict(source_fault='BLOCKED_BY_OVERLAY',fault_count=1,fault_at=4)),
        ('persistent-stale','UNCONFIRMED',dict(source_fault='STALE_TREE',fault_count=10000,budget_ms=300)),
        ('persistent-loading','UNCONFIRMED',dict(source_fault='PAGE_LOADING',fault_count=10000,budget_ms=300)),
        ('read-deadline','UNCONFIRMED',dict(read_delay_ms=150,budget_ms=100)),
        ('cancelled','UNCONFIRMED',dict(cancelled=True)),
        ('input-reject','FAILED',dict()),
    ]
    rows=[]
    for rep in range(repeats):
        for name,status,args in specs:
            rows.append(dict(case_id=f'safety-{name}-r{rep}',positive=False,repeat=rep,initial=[0,20,0,20],
                calls=[call('SetBrightness','bedroom_light',50)],fault='input_reject' if name=='input-reject' else 'normal',
                expected_status=status,arguments=args,expected_inputs=1 if name=='overlay-after' else 0))
    return rows
