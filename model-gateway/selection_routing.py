"""Optional deterministic name route and compact Jev; no execution authority."""
from catalog_uniqueness import explicit_name_id,guard_selection
from jev_selection import build_request,parse_selection,remote
from skill_selection import validate_selection


def compact_request(text,skills):
    body=build_request(text,skills)
    # Criteria already contain every name, goal and finalGoals. Keep that rubric
    # unchanged: this ablation only removes its duplicate in state.
    body['state']=dict(text=text)
    return body


def select_compact(text,skills,transport=remote):
    return guard_selection(text,skills,parse_selection(transport(compact_request(text,skills)),skills))


def select_routed(text,skills,transport=remote,compact=True):
    body=compact_request(text,skills) if compact else build_request(text,skills)
    identity=explicit_name_id(text,skills)
    if identity is not None:
        return validate_selection(dict(status='invoke',skill_id=identity,
            message='请核对该技能，确认前不会执行。 / Review this skill; nothing has run.'),skills)
    return guard_selection(text,skills,parse_selection(transport(body),skills))
