"""Author-labelled, frozen bilingual paired cases, independent of target screen geometry."""
import copy
import random


def call(skill,device,value):
    arg={'SetPower':'state','SetBrightness':'percent','SetTemperature':'celsius'}[skill]
    return {'skill':skill,'args':{'device':device,arg:value}}


def primary():
    rows=[]
    def add(skill,device,value,initial,text):
        rows.append(dict(case_id='p'+str(len(rows)).zfill(2),positive=True,initial=initial,
                         calls=[call(skill,device,value)],text=text,fault='normal'))
    add('SetPower','bedroom_light','on',[0,40,0,20],'Turn on the bedroom light.')
    add('SetPower','bedroom_light','off',[1,40,0,20],'关闭卧室灯。')
    add('SetPower','bedroom_ac','on',[0,40,0,20],'Turn on the bedroom air conditioner.')
    add('SetPower','bedroom_ac','off',[0,40,1,20],'关闭卧室空调。')
    for n,(target,initial) in enumerate([(20,80),(20,20),(50,20),(50,100),(80,20),(80,50),(80,80),(80,100)]):
        add('SetBrightness','bedroom_light',target,[1,initial,0,20],
            f'Set the bedroom light brightness to {target} percent.' if n%2==0 else f'把卧室灯亮度设为{target}%。')
    for n,(target,initial) in enumerate([(22,16),(22,22),(26,30),(26,26),(30,16),(30,30)]):
        add('SetTemperature','bedroom_ac',target,[0,40,1,initial],
            f'Set the bedroom AC temperature to {target} degrees Celsius.' if n%2==0 else f'把卧室空调温度设为{target}度。')
    rows.append(dict(case_id='p18',positive=True,initial=[0,20,0,20],fault='normal',
        text='Turn on the bedroom light, set brightness to 50 percent, turn on the AC, then set it to 26 degrees Celsius.',
        calls=[call('SetPower','bedroom_light','on'),call('SetBrightness','bedroom_light',50),call('SetPower','bedroom_ac','on'),call('SetTemperature','bedroom_ac',26)]))
    rows.append(dict(case_id='p19',positive=True,initial=[1,20,0,20],fault='normal',text='先把卧室灯亮度设为80%，然后设回20%。',
        calls=[call('SetBrightness','bedroom_light',80),call('SetBrightness','bedroom_light',20)]))
    assert len(rows)==20
    return rows


def challenges():
    rows=[]
    specs=[('normal',call('SetBrightness','bedroom_light',101),'Set bedroom light to 101 percent.','REJECTED'),
           ('normal',call('SetTemperature','bedroom_ac',15),'把卧室空调设为15度。','REJECTED'),
           ('normal',call('SetTemperature','bedroom_light',26),'Set the light temperature to 26 degrees Celsius.','REJECTED'),
           ('missing',call('SetBrightness','bedroom_light',80),'把卧室灯亮度设为80%。','UNRESOLVED'),
           ('duplicate',call('SetBrightness','bedroom_light',80),'Set bedroom light brightness to 80 percent.','AMBIGUOUS'),
           ('disabled',call('SetBrightness','bedroom_light',80),'把卧室灯亮度设为80%。','UNRESOLVED'),
           ('stubborn',call('SetBrightness','bedroom_light',80),'Set bedroom light brightness to 80 percent.','UNCONFIRMED'),
           ('normal',call('SetBrightness','bedroom_light',80),'把卧室灯亮度设为80%。','UNCONFIRMED')]
    for i,(fault,c,text,status) in enumerate(specs):
        rows.append(dict(case_id=f'n{i}',positive=False,initial=[1,20,0,20],fault=fault,calls=[c],text=text,
                         expected_status=status,cancelled=i==7))
    return rows


def cases(repeats=3):
    if type(repeats) is not int or not 1<=repeats<=5:raise ValueError('REPEATS')
    rows=[]
    for repeat in range(repeats):
        block=copy.deepcopy(primary()+challenges())
        random.Random(18431+repeat).shuffle(block)
        for row in block:row['case_id']+=f'-r{repeat}';row['repeat']=repeat
        rows.extend(block)
    return rows
