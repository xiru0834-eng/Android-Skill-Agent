"""Experimental identity gate and selective semantic review; not deployed."""
import re
from catalog_uniqueness import canonical
from jev_selection import build_request,remote as jev_remote,THRESHOLD
from skill_selection import select_skill,validate_selection
from compiler import remote as gpt_remote
from selection_routing import select_routed


def saved_reference(text,skills):
    """Recognize bounded explicit saved-name forms, not general language intent."""
    aliases={}
    for skill in skills:
        for alias in {skill['name'],*re.split(r'\s+/\s+',skill['name'])}:
            aliases.setdefault(canonical(alias),set()).add(skill['id'])
    names=[]
    patterns=[r'(?:运行|执行|启动)(?:我)?(?:已)?保存的(.{1,60}?)(?=[，。！？,.;!?]|$)',
              r'\bsaved\s+([\w\s\-\"“”\'「」]{1,60}?)\s+(?:workflow|routine|skill)\b']
    for pattern in patterns:
        for match in re.finditer(pattern,text,re.IGNORECASE):
            name=match.group(1).strip(' \t\n"“”\'「」')
            name=re.sub(r'(?:技能|流程)$','',name).strip(' \t\n"“”\'「」')
            names.append(canonical(name))
    if not names:return None,None
    if any(name not in aliases for name in names):return 'reject',None
    identities=set().union(*(aliases[name] for name in names))
    return (None,next(iter(identities))) if len(identities)==1 else ('clarify',None)


def select_accuracy(text,skills,jev_transport=jev_remote,gpt_transport=gpt_remote,review=False):
    build_request(text,skills)  # Validation before either local gate or remote request.
    blocked,bound=saved_reference(text,skills)
    def no(status):return validate_selection(dict(status=status,skill_id=None,
        message='所指技能不可唯一绑定，请核对当前目录。 / Check the named skill in the current catalog.'),skills)
    if blocked:return no(blocked)
    captured=[]
    def observe(body):
        response=jev_transport(body);captured.append(response);return response
    result=select_routed(text,skills,observe,compact=False)
    if result['status']=='invoke' and bound and result['skill_id']!=bound:return no('clarify')
    if not review or result['status']!='clarify' or not captured:return result
    answer=captured[0]['answers']['selection'];choice=answer['choice']
    if not choice.startswith('skill_'):return result
    suggested=skills[int(choice[6:])]
    if bound and suggested['id']!=bound:return no('clarify')
    if sum(s['finalGoals']==suggested['finalGoals'] for s in skills)>1:return result
    if answer['confidence']>=THRESHOLD and answer['probabilities'][choice]>=THRESHOLD:return result
    # One explicit second-model review, never on denial, structural ambiguity or error.
    reviewed=select_skill(text,skills,gpt_transport)
    if reviewed['status']=='invoke' and bound and reviewed['skill_id']!=bound:return no('clarify')
    return reviewed
