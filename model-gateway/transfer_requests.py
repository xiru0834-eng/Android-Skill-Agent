"""Separate durable requests withdrawn before dispatch from actual inputs.

This workflow has one request per unique step and never retries an input.
Aborts must follow that request and precede INPUT_RETURN.
"""


def dispatched_requests(journal,actions):
    requests={};aborted=set();returned=set()
    for event in journal:
        kind=event['kind']
        if kind not in ('INPUT_REQUEST','INPUT_ABORTED','INPUT_RETURN'):continue
        step=event['stepIndex']
        if kind=='INPUT_REQUEST':
            if step in requests:raise ValueError('Duplicate input request')
            requests[step]=event['data']['id']
        elif kind=='INPUT_ABORTED':
            if step not in requests or step in aborted or step in returned or requests[step]!=event['data']['id']:
                raise ValueError('Uncorrelated or late input abort')
            aborted.add(step)
        else:
            if step not in requests or step in aborted or step in returned:raise ValueError('Uncorrelated input return')
            returned.add(step)
    dispatched=[identifier for step,identifier in requests.items() if step not in aborted]
    if dispatched!=[action['id'] for action in actions]:raise ValueError('Requested inputs lost or aborted input dispatched')
    return dispatched
