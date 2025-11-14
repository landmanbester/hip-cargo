"""Generate all cab definitions for hip-cargo's own CLI commands."""

import subprocess
from pathlib import Path

# These are the CLI modules with @stimela_cab decorators and Annotated hints
CLI_MODULES = [
    "hip_cargo.cli.generate_cab",
    "hip_cargo.cli.generate_function",
]

CABS_DIR = Path("src/hip_cargo/cabs")
CABS_DIR.mkdir(exist_ok=True)

for module in CLI_MODULES:
    cmd_name = module.split(".")[-1]
    output = CABS_DIR / f"{cmd_name}.yaml"
    print(f"Generating {output}...")
    subprocess.run(
        [
            "cargo",
            "generate-cab",
            module,
            str(output),
        ],
        check=True,
    )

print("✓ All cabs generated successfully")
