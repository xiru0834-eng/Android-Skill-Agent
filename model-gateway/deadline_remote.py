"""Remaining-time transports for the experiment; old frozen adapters stay intact."""
import json
import os
import urllib.error
import urllib.request
from compiler import NoRedirect,ModelError,parse_response,ENDPOINT as GPT_ENDPOINT
from jev_selection import ENDPOINT as JEV_ENDPOINT,CREDENTIAL
from contracts import load_json,ContractError
from win_credentials import read_credential


def post(endpoint,body,key,timeout):
    request=urllib.request.Request(endpoint,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout) as reply:
            raw=reply.read(65537)
        if len(raw)>65536:raise ModelError('RESPONSE_SIZE')
        return load_json(raw.decode('utf-8').replace(key,'[REDACTED]'))
    except urllib.error.HTTPError as error:raise ModelError('HTTP_'+str(error.code)) from None
    except (TimeoutError,urllib.error.URLError):raise ModelError('NETWORK_OR_TIMEOUT') from None
    except (UnicodeError,ContractError):raise ModelError('MALFORMED_RESPONSE') from None


def gpt_remote(body,timeout):
    key=os.environ.get('OPENAI_API_KEY')
    if not key:raise ModelError('MISSING_API_KEY')
    try:return parse_response(post(GPT_ENDPOINT,body,key,timeout))
    except (KeyError,TypeError,AttributeError):raise ModelError('MALFORMED_RESPONSE') from None


def jev_remote(body,timeout):
    key=read_credential(CREDENTIAL,'utf-16-le')
    if not key.startswith('apikey_') or len(key)>2000:raise ModelError('INVALID_JEV_CREDENTIAL')
    return post(JEV_ENDPOINT,body,key,timeout)
