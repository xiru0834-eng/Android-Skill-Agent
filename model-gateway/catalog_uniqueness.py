"""Conservative gate for equivalent goals; not a general language parser."""
import re
import unicodedata
from skill_selection import validate_catalog,validate_selection,utf16_length


def canonical(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',value).strip()).casefold()


def explicit_name_id(text,skills):
    aliases={}
    for skill in skills:
        for name in {skill['name'],*re.split(r'\s+/\s+',skill['name'])}:
            aliases.setdefault(canonical(name),set()).add(skill['id'])
    command=canonical(text); matches=set()
    for name,identities in aliases.items():
        escaped=re.escape(name)
        quoted='(?:'+ '|'.join([escaped,'"'+escaped+'"',"'"+escaped+"'",'“'+escaped+'”','「'+escaped+'」'])+')'
        patterns=[r'(?:please )?(?:run|execute|start|activate) (?:(?:my |the )?saved )?'+quoted+r'(?: (?:workflow|skill))?[.!。！]?',
                  r'(?:请(?:你)?(?:现在)?)?(?:执行|运行|启动)(?:我保存的|保存的|名为)?'+quoted+r'(?:技能|流程)?[.!。！]?']
        if any(re.fullmatch(pattern,command) for pattern in patterns): matches.update(identities)
    return next(iter(matches)) if len(matches)==1 else None


def model_named_identity(text,skills):
    """Bounded identity evidence, never a model-free authorization path.

    Full-sentence templates exclude surrounding quotes/history/conditions and
    changed parameters. The semantic proposal must independently agree on ID.
    Unsupported phrasings still clarify rather than guessing a substring.
    """
    command=canonical(text);matches=set()
    for skill in skills:
        for name in {skill['name'],*re.split(r'\s+/\s+',skill['name'])}:
            escaped=re.escape(canonical(name))
            quoted='(?:'+'|'.join([escaped,'"'+escaped+'"',"'"+escaped+"'",'“'+escaped+'”','「'+escaped+'」'])+')'
            patterns=[
                r'(?:please )?(?:use|run|execute|activate|start) (?:the |my )?(?:existing|saved) '
                r'(?:workflow|skill|routine) (?:named|called) '+quoted+
                r'(?: now)?(?:,? (?:as saved|unchanged|without changing (?:any )?settings|not another one with identical targets))?[.!]?',
                r'(?:请(?:你)?)?(?:现在)?(?:用|使用|运行|执行|启动)(?:名称为|名为|叫)'+quoted+
                r'的(?:那条|这条)?(?:已有|已保存|保存的)(?:技能|流程)'
                r'(?:[，,](?:保持原样|其他同目标的不选|不修改设置))?[。！.!]?']
            if any(re.fullmatch(p,command) for p in patterns):matches.add(skill['id'])
    return next(iter(matches)) if len(matches)==1 else None


def guard_selection(text,skills,selection):
    validate_catalog(skills); validate_selection(selection,skills)
    if not isinstance(text,str) or not text.strip() or utf16_length(text)>500: raise ValueError('INVALID_TEXT')
    if selection['status']!='invoke': return selection
    selected=next(s for s in skills if s['id']==selection['skill_id'])
    if selected.get('processMode')=='ORDERED' and selected['id'] not in (explicit_name_id(text,skills),model_named_identity(text,skills)):
        return dict(status='clarify',skill_id=None,message='请按名称调用这条有序技能，不能只根据最终状态推断过程。 / Run this ordered skill by name; final goals do not specify its process.')
    equivalent=[s for s in skills if s['finalGoals']==selected['finalGoals']]
    if len(equivalent)==1 or selected['id'] in (explicit_name_id(text,skills),model_named_identity(text,skills)): return selection
    return dict(status='clarify',skill_id=None,
        message='有多条技能达到相同目标，请明确输入“执行技能名”。 / Multiple skills share these targets; use "Run skill name".')
