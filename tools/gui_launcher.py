import sys

from xsave.errors import FormatError
from xsave.gui import main, run_command


def failure(message):
    text = str(message)
    text = (text if text.startswith('xsave:') else 'xsave: ' + text) + '\n'
    if sys.stderr is not None:
        sys.stderr.write(text)
    elif sys.platform == 'win32':
        # PyInstaller windowed mode removes Python stderr, not inherited pipes.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = (wintypes.DWORD,)
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.WriteFile.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
        data, written = text.encode('utf-8'), wintypes.DWORD()
        buffer = ctypes.create_string_buffer(data)
        kernel.WriteFile(kernel.GetStdHandle(-12), buffer, len(data), ctypes.byref(written), None)
        kernel.OutputDebugStringW.argtypes = (wintypes.LPCWSTR,)
        kernel.OutputDebugStringW(text)
    return 2


if __name__ == '__main__':
    if sys.argv[1:2] == ['--cli']:
        # Windowed builds have no stdout; require the CLI's safe report file.
        if '--report' not in sys.argv[2:]:
            raise SystemExit(failure('--cli requires a new --report path.'))
        try:
            run_command(sys.argv[2:])
        except (FormatError, OSError) as exc:
            raise SystemExit(failure(exc))
    else:
        main()
