"""Sequential batch orchestration; individual converters remain the safety boundary."""
from pathlib import Path
import tempfile

from . import __version__
from .converter import _destination, _publish_tree, _select, to_xbox, to_xenia
from .errors import FormatError
from .paths import read_file
from .stfs import StfsPackage
from .xenia import discover

MAX_BATCH = 256


def convert_batch(direction, source, output, *, packages=None, template=None,
                  title_id=None, source_xuid=None, profile_id=None, device_id=None,
                  signer=None, unsigned=False, xuid=None, layout='canary',
                  allow_unsafe=False, backup_dir=None):
    if direction not in ('to-xbox', 'to-xenia'):
        raise FormatError('Unknown batch direction')
    source = Path(source).absolute()
    saves = discover(source, title_id=title_id, xuid=source_xuid)
    names = [s.package_name for s in saves]
    if len({name.casefold() for name in names}) != len(names):
        raise FormatError('Batch package names are ambiguous; choose a narrower input folder')
    if packages is not None:
        if not packages or len(set(packages)) != len(packages) or any(name not in names for name in packages):
            raise FormatError('Batch selection is empty, duplicated or not present in the input')
        saves = [s for s in saves if s.package_name in packages]
    if len(saves) > MAX_BATCH:
        raise FormatError(f'Batch exceeds {MAX_BATCH} packages; choose a narrower input')
    inputs = tuple(dict.fromkeys(p for save in saves for p in save.input_paths))
    target_profile = None
    if direction == 'to-xbox':
        if template is None:
            raise FormatError('Batch Xbox output requires a same-title CON template')
        template = Path(template).absolute()
        donor_data = read_file(template)
        donor = StfsPackage(donor_data)
        if donor.magic != b'CON ' or donor.metadata.content_type != 1:
            raise FormatError('A CON Saved Game template is required')
        if any(save.title_id != donor.metadata.title_id for save in saves):
            raise FormatError('Every selected Title ID must match the shared template; split games into separate batches')
        target_profile = donor.metadata.profile_id if profile_id is None else profile_id
        if not isinstance(target_profile, bytes) or len(target_profile) != 8:
            raise FormatError('Profile ID must be exactly eight bytes')
        inputs += (template,)
    output = Path(output).absolute()
    backup_dir = Path(backup_dir).absolute() if backup_dir is not None else output.parent / '.xsave-backups'
    output = _destination(output, (*inputs, backup_dir))
    _destination(backup_dir / 'snapshot-check', inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.xsave-batch-') as temporary:
        stage = Path(temporary) / 'result'
        stage.mkdir()
        for index, save in enumerate(saves):
            item = Path(temporary) / f'item-{index}'
            row = {'package': save.package_name, 'title_id': f'{save.title_id:08X}'}
            try:
                common = dict(package=save.package_name, title_id=title_id, source_xuid=source_xuid,
                              allow_unsafe=allow_unsafe, backup_dir=backup_dir)
                if _select(source, save.package_name, title_id, source_xuid) != save:
                    raise FormatError('Input changed after batch discovery; item aborted')
                # shortcut: reuse per-item rediscovery; optimize only after measured large-batch latency.
                if direction == 'to-xbox':
                    if read_file(template) != donor_data:
                        raise FormatError('Template changed after batch discovery; item aborted')
                    report = to_xbox(source, template, item, profile_id=profile_id, device_id=device_id,
                                     signer=signer, unsigned=unsigned, **common)
                else:
                    report = to_xenia(source, item, xuid=xuid, layout=layout, **common)
            except (FormatError, OSError) as exc:
                row.update(status='failed', error=str(exc))
                rows.append(row)
                continue
            # Staging errors abort the batch so failed items cannot leak partial files.
            if direction == 'to-xbox':
                relative = Path('Content') / report['profile_id'] / report['title_id'] / '00000001' / save.package_name
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                item.rename(destination)
                report['output'] = str(output / relative)
            else:
                entries = sorted(item.rglob('*'))
                for entry in entries:
                    destination = stage / entry.relative_to(item)
                    if destination.exists() and not (entry.is_dir() and destination.is_dir()):
                        raise FormatError('Batch Xenia output paths collide')
                for entry in entries:
                    destination = stage / entry.relative_to(item)
                    if entry.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        entry.rename(destination)
                report['output'] = str(output)
            row.update(status='success', report=report)
            rows.append(row)
        succeeded = sum(row['status'] == 'success' for row in rows)
        if succeeded:
            _publish_tree(stage, output)
    failed = len(rows) - succeeded
    return {'tool_version': __version__, 'direction': direction,
            'status': 'batch_complete' if not failed else 'batch_partial' if succeeded else 'batch_failed',
            'total': len(rows), 'succeeded': succeeded, 'failed': failed,
            'output': str(output) if succeeded else None, 'results': rows,
            'xenia_runtime_test': 'not_tested', 'retail_console_test': 'not_tested'}
