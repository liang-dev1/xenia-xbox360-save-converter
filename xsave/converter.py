"""Backup-first conversion, with separate container and game-level evidence."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import os
import tempfile
import zipfile

from .adapters import adapt
from . import __version__
from .errors import FormatError
from .paths import is_link, read_file, read_tree
from .signing import verify_con_signature
from .stfs import StfsPackage, build
from .xenia import discover, write_save


def _read(path):
    return read_file(Path(path))


def _publish_tree(stage, output):
    if os.name == 'nt':
        stage.rename(output)
    else:
        # Exclusive creation prevents replacing an existing POSIX directory.
        output.mkdir()
        for child in stage.iterdir():
            child.rename(output / child.name)


def _destination(output, inputs):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FormatError('Refuse to overwrite an existing output')
    for parent in (output.parent, *output.parents):
        if is_link(parent):
            raise FormatError('Output must not traverse links/junctions')
    target = output.resolve()
    for source in inputs:
        source = Path(source).resolve()
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise FormatError('Output/backup must not overlap input')
    return output


def backup(inputs, directory):
    """Verified snapshot; signing keys are deliberately not inputs to this API."""
    sources = list(dict.fromkeys(Path(p).absolute() for p in inputs))
    directory = Path(directory).absolute()
    _destination(directory / 'snapshot-check', sources)
    blobs, manifest = {}, []
    for i, source in enumerate(sources):
        if source.is_dir():
            files, dirs = read_tree(source)
        else:
            files, dirs = {source.name: _read(source)}, set()
        entries = {}
        for name, blob in files.items():
            digest = sha256(blob).hexdigest()
            entries[name] = digest
            blobs[f'{i}/{name}'] = blob
        manifest.append({'source': str(source), 'directories': sorted(dirs), 'files': entries})
    encoded = json.dumps(manifest, sort_keys=True).encode()
    digest = sha256(encoded).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + '.zip')
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=directory, prefix='.backup-') as temporary:
            stage = Path(temporary) / 'snapshot.zip'
            with zipfile.ZipFile(stage, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', encoded)
                for name, blob in blobs.items():
                    archive.writestr(name, blob)
            _verify_backup(stage, encoded, blobs)
            stage.rename(target)
    _verify_backup(target, encoded, blobs)
    return target


def _verify_backup(path, encoded, blobs):
    with zipfile.ZipFile(path) as archive:
        if archive.read('manifest.json') != encoded or archive.testzip() is not None:
            raise FormatError('Backup manifest/CRC verification failed')
        for name, blob in blobs.items():
            if archive.read(name) != blob:
                raise FormatError('Backup data verification failed')


def _select(source, package=None, title_id=None, source_xuid=None):
    saves = discover(Path(source), title_id=title_id, xuid=source_xuid)
    if package is not None:
        saves = [save for save in saves if save.package_name == package]
    if len(saves) != 1:
        raise FormatError(f'Found {len(saves)} packages; select one with --package')
    return saves[0]


def _provenance(before, after):
    return {name: {'input_sha256': sha256(blob).hexdigest(),
                   'output_sha256': sha256(after[name]).hexdigest(),
                   'changed': blob != after[name]}
            for name, blob in sorted(before.items())}


def _report(save, result, snapshot, output):
    return {'tool_version': __version__, 'title_id': f'{save.title_id:08X}', 'content_type': '00000001',
            'package': save.package_name, 'output': str(output), 'backup': str(snapshot),
            'adapter': result.adapter, 'payload_integrity': 'checked' if result.checked else 'unknown',
            'file_provenance': _provenance(save.files, result.files),
            'warnings': sorted(set(save.warnings + result.warnings)),
            'safety': 'unsafe_identity_change' if 'unsafe_identity_change' in result.warnings else
                      'known_adapter_checks_only' if result.checked else 'opaque_payload_unverified',
            'certificate_issuer_trust': 'not_verified', 'retail_console_test': 'not_tested',
            'xenia_runtime_test': 'not_tested'}


def to_xbox(source, template, output, *, package=None, title_id=None,
            source_xuid=None, profile_id=None, device_id=None, signer=None,
            unsigned=False, allow_unsafe=False, backup_dir=None):
    save = _select(source, package, title_id, source_xuid)
    template = Path(template).absolute()
    donor_data = _read(template)
    donor = StfsPackage(donor_data)
    if donor.magic != b'CON ' or donor.metadata.content_type != 1 or donor.metadata.title_id != save.title_id:
        raise FormatError('A same-title CON Saved Game donor is required')
    target = donor.metadata.profile_id if profile_id is None else profile_id
    if not isinstance(target, bytes) or len(target) != 8:
        raise FormatError('Profile ID must be exactly eight bytes')
    if device_id is not None and (not isinstance(device_id, bytes) or len(device_id) != 20):
        raise FormatError('Device ID must be exactly twenty bytes')
    result = adapt(save.title_id, save.files, save.xuid, int.from_bytes(target, 'big'), allow_unsafe=allow_unsafe)
    inputs = (*save.input_paths, template)
    snapshot_directory = backup_dir or Path(output).absolute().parent / '.xsave-backups'
    output = _destination(output, (*inputs, snapshot_directory))
    preserved = (result.files == donor.files and save.directories == donor.directories
                 and target == donor.metadata.profile_id
                 and (device_id is None or device_id == donor.metadata.device_id)
                 and save.display_name == donor.metadata.display_name
                 and (save.thumbnail is None or save.thumbnail == donor.thumbnail))
    original_signature = verify_con_signature(donor_data)
    if signer is None and not unsigned and not (preserved and original_signature == 'valid'):
        raise FormatError('Donor signatures cannot authorize changed data; supply --keyvault or explicitly --unsigned')
    if signer is not None and unsigned:
        raise FormatError('Choose key-backed signing or unsigned draft, not both')
    snapshot = backup(inputs, snapshot_directory)
    fresh = _select(source, package, title_id, source_xuid)
    if fresh != save or _read(template) != donor_data:
        raise FormatError('Input changed during backup; conversion aborted')
    data = donor_data if preserved and signer is None and not unsigned else build(
        result.files, donor_data, save.directories, profile_id=target, device_id=device_id,
        display_name=save.display_name, thumbnail=save.thumbnail, signer=signer)
    rebuilt = StfsPackage(data)
    if rebuilt.files != result.files or rebuilt.directories != save.directories or rebuilt.metadata.profile_id != target:
        raise FormatError('Output metadata/file-tree verification failed')
    signature = verify_con_signature(data)
    if signer is not None and signature != 'valid':
        raise FormatError('Signed output failed content RSA verification')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.xsave-') as temporary:
        stage = Path(temporary) / 'package'
        stage.write_bytes(data)
        if StfsPackage(stage.read_bytes()).files != result.files:
            raise FormatError('Written output differs from verified data')
        # Windows rename refuses replacement; POSIX link provides that guarantee.
        if os.name == 'nt':
            stage.rename(output)
        else:
            os.link(stage, output)
    report = _report(save, result, snapshot, output)
    report.update(status='signed_needs_console_test' if signer is not None else
                  'preserved_donor_signature' if not unsigned else 'unsigned_draft',
                  container=rebuilt.validate(), output_sha256=sha256(data).hexdigest(),
                  profile_id=target.hex().upper())
    report['metadata'] = {
        'source_xuid': f'{save.xuid:016X}' if save.xuid is not None else None,
        'template_profile_id': donor.metadata.profile_id.hex().upper(),
        'template_device_id': donor.metadata.device_id.hex().upper(),
        'template_console_id': donor.metadata.console_id.hex().upper(),
        'output_profile_id': rebuilt.metadata.profile_id.hex().upper(),
        'output_device_id': rebuilt.metadata.device_id.hex().upper(),
        'output_console_id': rebuilt.metadata.console_id.hex().upper(),
    }
    if unsigned:
        report['warnings'].append('unsigned_output_not_retail_acceptable')
    return report


def to_xenia(source, output, *, xuid=None, layout='canary', package=None,
             title_id=None, source_xuid=None, allow_unsafe=False, backup_dir=None):
    save = _select(source, package, title_id, source_xuid)
    identity = save.xuid if xuid is None else xuid
    result = adapt(save.title_id, save.files, save.xuid, identity, allow_unsafe=allow_unsafe)
    snapshot_directory = backup_dir or Path(output).absolute().parent / '.xsave-backups'
    output = _destination(output, (*save.input_paths, snapshot_directory))
    snapshot = backup(save.input_paths, snapshot_directory)
    if _select(source, package, title_id, source_xuid) != save:
        raise FormatError('Input changed during backup; conversion aborted')
    exported = replace(save, files=result.files, xuid=identity)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.xsave-') as temporary:
        stage = Path(temporary) / 'content'
        write_save(exported, stage, layout=layout)
        check = discover(stage)
        if len(check) != 1 or check[0].files != result.files or check[0].title_id != save.title_id:
            raise FormatError('Xenia output rediscovery/file verification failed')
        _publish_tree(stage, output)
    report = _report(save, result, snapshot, output)
    report.update(status='xenia_export_needs_runtime_test', layout=layout,
                  xuid=f'{identity:016X}' if identity is not None else None,
                  source_container=save.container_validation,
                  container={'file_tree': 'valid', 'metadata_rediscovery': 'valid'})
    return report
