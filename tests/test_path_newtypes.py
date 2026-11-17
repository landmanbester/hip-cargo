"""File/Directory/MS/URI are one set of UPath-backed NewTypes, owned by hip-cargo (#114)."""

from pathlib import Path

import pytest
import yaml
from upath import UPath

import hip_cargo
from hip_cargo.core.generate_function import generate_function


@pytest.mark.parametrize("name", ["File", "Directory", "MS", "URI"])
def test_path_types_are_exported_and_upath_backed(name: str) -> None:
    path_type = getattr(hip_cargo, name)
    assert path_type.__supertype__ is UPath
    assert name in hip_cargo.__all__


def test_generated_module_imports_path_types_from_hip_cargo(tmp_path: Path) -> None:
    cab = {
        "cabs": {
            "render": {
                "info": "Render.",
                "command": "my_pkg.core.render.render",
                "inputs": {
                    "ms": {"dtype": "MS", "required": True, "info": "Input."},
                    "extra": {"dtype": "List[File]", "info": "Extras."},
                },
                "outputs": {"out": {"dtype": "Directory", "info": "Output."}},
            }
        }
    }
    cab_file = tmp_path / "render.yml"
    cab_file.write_text(yaml.safe_dump(cab, sort_keys=False))
    output_file = tmp_path / "render.py"
    generate_function(cab_file, output_file=output_file)
    code = output_file.read_text()

    assert "NewType" not in code
    assert "pathlib" not in code
    namespace: dict[str, object] = {}
    exec(compile(code, str(output_file), "exec"), namespace)
    for name in ["MS", "File", "Directory"]:
        assert namespace[name] is getattr(hip_cargo, name)
