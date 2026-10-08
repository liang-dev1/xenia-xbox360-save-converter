"""Explicit game compatibility seam; the container module has no game IDs."""
from dataclasses import dataclass

from ..errors import FormatError


@dataclass
class AdapterResult:
    files: dict[str, bytes]
    adapter: str
    checked: bool
    warnings: list[str]


def adapt(title_id: int, files: dict[str, bytes], source_identity: int | None,
          target_identity: int | None, *, allow_unsafe: bool = False) -> AdapterResult:
    from .ngii import TITLE_ID, transform
    registry = {TITLE_ID: transform}
    if title_id in registry:
        return registry[title_id](files, source_identity, target_identity, allow_unsafe=allow_unsafe)
    changed = source_identity is not None and target_identity is not None and source_identity != target_identity
    warnings = ['opaque_payload', 'game_integrity_not_checked']
    if changed:
        if not allow_unsafe:
            raise FormatError('Unknown game identity change requires an adapter or --allow-unsafe; payload binding cannot be repaired generically')
        warnings.append('unsafe_identity_change')
    if source_identity is None:
        warnings.append('source_payload_identity_unknown')
    return AdapterResult(dict(files), 'opaque', False, warnings)
