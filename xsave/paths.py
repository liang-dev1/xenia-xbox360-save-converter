"""Portable paths for untrusted package entries and host writes."""
from pathlib import Path, PurePosixPath
import os

from .errors import FormatError

MAX_BYTES = 256 * 1024 * 1024
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def safe_component(name: str, max_bytes: int | None = None) -> str:
    if not name or name in ('.', '..') or name.endswith((' ', '.')):
        raise FormatError(f'Unsafe empty/dot/trailing filename: {name!r}')
    if any(ord(c) < 32 or c in '/\\:*?"<>|' for c in name) or name.split('.')[0].upper() in _RESERVED:
        raise FormatError(f'Unsafe portable filename: {name!r}')
    try:
        encoded = name.encode('ascii')
    except UnicodeEncodeError as exc:
        raise FormatError('STFS/XCONTENT names must be ASCII in this version') from exc
    if max_bytes is not None and len(encoded) > max_bytes:
        raise FormatError(f'Filename exceeds {max_bytes} bytes: {name!r}')
    return name


def safe_path(name: str) -> str:
    if '\\' in name or name.startswith('/') or not name:
        raise FormatError(f'Unsafe relative path: {name!r}')
    for part in name.split('/'):
        safe_component(part)
    return PurePosixPath(name).as_posix()


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def read_file(path: Path, limit: int = MAX_BYTES) -> bytes:
    path = Path(path).absolute()
    if any(is_link(p) for p in (path, *path.parents)) or not path.is_file():
        raise FormatError('Expected a regular file without links/junctions')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise FormatError('Input file exceeds resource limit')
    return data


def read_tree(root: Path) -> tuple[dict[str, bytes], set[str]]:
    root = Path(root).absolute()
    if any(is_link(p) for p in (root, *root.parents)):
        raise FormatError('Symbolic links/junctions are not accepted as inputs')
    files, directories, seen = {}, set(), set()
    total = 0
    def walk_error(error):
        raise FormatError('Unable to read complete input tree') from error
    for directory, child_dirs, child_files in os.walk(root, followlinks=False, onerror=walk_error):
        child_dirs.sort()
        for child in sorted(child_dirs + child_files):
            path = Path(directory) / child
            if is_link(path):
                raise FormatError(f'Symbolic link/junction in input: {path.name}')
            name = safe_path(path.relative_to(root).as_posix())
            if name.casefold() in seen:
                raise FormatError('Case-insensitive path collision in input')
            seen.add(name.casefold())
            if len(seen) > 100000:
                raise FormatError('Input exceeds filesystem entry limit')
            if path.is_dir():
                directories.add(name)
            elif path.is_file():
                data = read_file(path, MAX_BYTES - total)
                total += len(data)
                files[name] = data
            else:
                raise FormatError(f'Unsupported filesystem entry: {name}')
    return files, directories
