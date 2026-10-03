"""Windows current-user DPAPI storage and stdio launch; no provider credentials."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys


def transform(data: bytes, *, decrypt=False) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('Windows current-user protection is required')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    name = 'CryptUnprotectData' if decrypt else 'CryptProtectData'
    function = getattr(crypt, name)
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    # CRYPTPROTECT_UI_FORBIDDEN, current Windows user (never LOCAL_MACHINE).
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError('Windows credential protection failed')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def main():
    try:
        path = Path(__file__).resolve().with_name('worker.dpapi')
        if path.stat().st_size > 16384:
            raise ValueError('Credential file too large')
        token = transform(path.read_bytes(), decrypt=True).decode('ascii')
        if not token or len(token) > 4096 or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError('Credential invalid')
        os.environ['YS_AIMEMORY_TOKEN'] = token
        import bridge
        return bridge.main()
    except Exception as exc:
        sys.stderr.write('credential_launcher_stopped: ' + type(exc).__name__ + '\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
