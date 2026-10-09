"""Windows Credential Manager adapter; no plaintext key file and no key logging."""
import ctypes as c
from ctypes import wintypes as w
import os

TARGET = 'DemoProbe/OpenAI'


class Credential(c.Structure):
    _fields_ = [('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),('Comment',w.LPWSTR),
                ('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),('CredentialBlob',c.POINTER(c.c_ubyte)),
                ('Persist',w.DWORD),('AttributeCount',w.DWORD),('Attributes',c.c_void_p),
                ('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]


def api():
    if os.name != 'nt': raise RuntimeError('WINDOWS_CREDENTIALS_UNAVAILABLE')
    dll=c.WinDLL('Advapi32.dll',use_last_error=True)
    dll.CredWriteW.argtypes=[c.POINTER(Credential),w.DWORD]; dll.CredWriteW.restype=w.BOOL
    dll.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.POINTER(c.POINTER(Credential))]; dll.CredReadW.restype=w.BOOL
    dll.CredFree.argtypes=[c.c_void_p]
    return dll


def store_key(key):
    if not isinstance(key,str) or not key.startswith('sk-') or len(key)>2000: raise ValueError('INVALID_KEY')
    blob=key.encode('utf-8'); buffer=(c.c_ubyte*len(blob)).from_buffer_copy(blob)
    cred=Credential(Type=1,TargetName=TARGET,UserName='DemoProbe',Persist=2,
                    CredentialBlobSize=len(blob),CredentialBlob=buffer)
    if not api().CredWriteW(c.byref(cred),0): raise RuntimeError('CREDENTIAL_SAVE_FAILED')


def read_credential(target,encoding='utf-8'):
    dll=api(); pointer=c.POINTER(Credential)()
    if not dll.CredReadW(target,1,0,c.byref(pointer)): raise RuntimeError('CREDENTIAL_NOT_CONFIGURED')
    try: return c.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode(encoding)
    finally: dll.CredFree(pointer)


def read_key():
    try:return read_credential(TARGET)
    except RuntimeError:raise RuntimeError('OPENAI_KEY_NOT_CONFIGURED') from None
