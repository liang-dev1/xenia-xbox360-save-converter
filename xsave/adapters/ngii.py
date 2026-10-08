"""NGII story/system compatibility, independent from STFS offsets/layout."""
import re
import struct

from ..errors import FormatError
from . import AdapterResult

TITLE_ID = 0x544307D5
STORY_HEADER = bytes.fromhex('0000788000000006000000000123456701000000012345670000000000000000')


def checksum(data: bytes, offset: int) -> int:
    return sum(struct.unpack(f'>{offset // 4}I', data[:offset])) & 0xffffffff


def transform(files: dict[str, bytes], source_identity: int | None,
              target_identity: int | None, *, allow_unsafe: bool = False) -> AdapterResult:
    result = dict(files)
    checked = 0
    warnings = []
    changed = source_identity is not None and target_identity is not None and source_identity != target_identity
    for path, original in files.items():
        name = path.rsplit('/', 1)[-1].lower()
        if name == 'ng2sysd.dat':
            if len(original) != 2048:
                raise FormatError('NGII system payload must be 2048 bytes')
            offset = 0x768
        elif re.fullmatch(r'ng2stryd\d{2}\.dat', name):
            if len(original) != 31744 or original[:32] != STORY_HEADER:
                raise FormatError('Unsupported NGII story size/header/version')
            offset = 0x7880
        else:
            warnings.append(f'game_integrity_not_checked:{path}')
            if changed and not allow_unsafe:
                raise FormatError(f'NGII adapter does not support identity changes for {path}; use --allow-unsafe only for a deliberately unsafe test')
            if changed:
                warnings.append('unsafe_identity_change')
            continue
        if checksum(original, offset) != int.from_bytes(original[offset:offset + 4], 'big'):
            raise FormatError(f'NGII checksum invalid: {path}')
        checked += 1
        if name == 'ng2sysd.dat' and target_identity is not None:
            embedded = int.from_bytes(original[:8], 'big')
            if source_identity is not None and embedded != source_identity:
                warnings.append('source_system_xuid_differs_from_container_identity')
            if embedded != target_identity:
                data = bytearray(original)
                data[:8] = target_identity.to_bytes(8, 'big')
                data[offset:offset + 4] = checksum(data, offset).to_bytes(4, 'big')
                result[path] = bytes(data)
    return AdapterResult(result, 'ngii', checked == len(files) and checked > 0, warnings)
