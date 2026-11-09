"""Windows-only credential storage. No plaintext fallback."""
import ctypes
from ctypes import wintypes as w
from .jobs import JobError

class Credential(ctypes.Structure):
    _fields_=[('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),('Comment',w.LPWSTR),('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),('Persist',w.DWORD),('AttributeCount',w.DWORD),('Attributes',ctypes.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]

class KeyStore:
    def __init__(self,target='SpeechToNote/Gemini'):
        self.target=target
    def _api(self):
        api=ctypes.WinDLL('Advapi32.dll',use_last_error=True)
        api.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))]
        api.CredWriteW.argtypes=[ctypes.POINTER(Credential),w.DWORD]
        api.CredDeleteW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD]
        api.CredFree.argtypes=[ctypes.c_void_p]
        return api
    def get(self):
        try:
            api=self._api(); pointer=ctypes.POINTER(Credential)()
            if not api.CredReadW(self.target,1,0,ctypes.byref(pointer)):
                if ctypes.get_last_error()==1168:return None
                raise OSError()
            try:return ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize).decode('utf-8')
            finally:api.CredFree(pointer)
        except Exception:
            raise JobError(500,'CREDENTIAL_STORE_FAILED','Windows 자격 증명 저장소에 접근하지 못했습니다.') from None
    def set(self,key):
        try:
            blob=key.encode('utf-8')
            if len(blob)>2560:raise ValueError()
            buffer=(ctypes.c_ubyte*len(blob)).from_buffer_copy(blob)
            item=Credential(Type=1,TargetName=self.target,CredentialBlobSize=len(blob),CredentialBlob=buffer,Persist=2,UserName='SpeechToNote')
            if not self._api().CredWriteW(ctypes.byref(item),0):raise OSError()
        except Exception:
            raise JobError(500,'CREDENTIAL_STORE_FAILED','키를 안전하게 저장하지 못했습니다. 일반 파일에는 저장하지 않았습니다.') from None
    def delete(self):
        try:
            if not self._api().CredDeleteW(self.target,1,0) and ctypes.get_last_error()!=1168:raise OSError()
        except Exception:
            raise JobError(500,'CREDENTIAL_STORE_FAILED','키를 삭제하지 못했습니다.') from None
