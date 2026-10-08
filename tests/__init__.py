"""Keep all disposable test files inside the project workspace."""
from pathlib import Path
import tempfile

_temporary_root = Path(__file__).resolve().parents[1] / '.local' / 'tmp'
_temporary_root.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_temporary_root)
