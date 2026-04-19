"""Container fallback execution for hip-cargo CLI commands."""

import os
import shutil
import subprocess
import sys
import types
import typing
from pathlib import Path, PurePath

from upath import UPath

from hip_cargo.utils.metadata import StimelaMeta

CONTAINER_RUNTIMES = ["apptainer", "singularity", "docker", "podman"]

_EXTRA_FOR_SCHEME: dict[str, str] = {
    "s3": "hip-cargo[s3]",
    "gs": "hip-cargo[gcs]",
    "gcs": "hip-cargo[gcs]",
    "az": "hip-cargo[azure]",
    "abfs": "hip-cargo[azure]",
    "adl": "hip-cargo[azure]",
}


def _extras_hint_from_argv(argv: list[str]) -> str:
    """Scan argv for remote URIs and return a `pip install` hint."""
    hints: set[str] = set()
    for arg in argv:
        for scheme, extra in _EXTRA_FOR_SCHEME.items():
            if arg.startswith(f"{scheme}://"):
                hints.add(extra)
    return ", ".join(sorted(hints))


def run_in_container(
    func: typing.Callable,
    params: dict[str, typing.Any],
    image: str,
    backend: str = "auto",
    always_pull_images: bool = False,
) -> None:
    """Run a CLI command inside a container, mounting required volumes.

    Args:
        func: The decorated CLI function.
        params: Parameter name → value dict (excludes backend).
        image: Full container image reference (e.g. "ghcr.io/user/repo:tag").
        backend: Container runtime to use, or "auto" to detect.
        always_pull_images: Force re-pull of the container image even if cached locally.
    """
    runtime = _detect_runtime(backend)
    mounts = _resolve_mounts(func, params)
    protocols = _collect_remote_protocols(func, params)
    cred_env = _build_credential_env(protocols, dict(os.environ))
    cred_mounts, _gcs_keyfile = _build_credential_mounts(protocols, dict(os.environ), home=os.path.expanduser("~"))
    cwd = os.getcwd()
    # Ensure cwd is mounted read-write
    mounts[cwd] = True
    cli_args = _build_argv_with_native_backend()

    if always_pull_images:
        _pull_image(runtime, image)

    cmd = _build_container_cmd(runtime, image, mounts, cwd, cli_args, cred_env=cred_env, cred_mounts=cred_mounts)

    print(f"Falling back to container execution ({runtime})")
    print(f"  Image: {image}")
    print(f"  Command: {' '.join(cli_args)}")
    subprocess.run(cmd, check=True)


def _detect_runtime(backend: str) -> str:
    """Find an available container runtime.

    Args:
        backend: Specific runtime name, or "auto" to detect.

    Returns:
        Name of the container runtime executable.
    """
    if backend != "auto":
        if shutil.which(backend):
            return backend
        raise RuntimeError(f"Container runtime '{backend}' not found on PATH.")

    for runtime in CONTAINER_RUNTIMES:
        if shutil.which(runtime):
            return runtime

    hint = _extras_hint_from_argv(sys.argv)
    msg = (
        "No container runtime found. Install one of: "
        + ", ".join(CONTAINER_RUNTIMES)
        + "\nOr install the full package dependencies to run natively."
    )
    if hint:
        msg += f"\nFor remote URIs, install the relevant extra: {hint}"
    raise RuntimeError(msg)


def _pull_image(runtime: str, image: str) -> None:
    """Force pull/refresh a container image.

    Args:
        runtime: Container runtime name.
        image: Container image reference.
    """
    if runtime in ("apptainer", "singularity"):
        pull_image = image
        if not image.endswith(".sif") and "://" not in image:
            pull_image = f"docker://{image}"
        print(f"Pulling image: {pull_image}")
        subprocess.run([runtime, "pull", "--force", pull_image], check=True)
    else:  # docker, podman
        print(f"Pulling image: {image}")
        subprocess.run([runtime, "pull", image], check=True)


def _resolve_mounts(func: typing.Callable, params: dict[str, typing.Any]) -> dict[str, bool]:
    """Determine volume mounts from function type hints and parameter values.

    Follows stimela's mounting conventions:
    - Input paths are mounted read-only, output paths read-write.
    - If a path doesn't exist, mount its parent directory instead.
    - path_policies.write_parent: mount parent directory in rw mode.
    - path_policies.access_parent: mount parent directory (in ro mode unless write_parent).
    - mkdir: implies parent needs rw access.

    Returns:
        Dict mapping absolute directory paths to read-write flag (True=rw, False=ro).
    """
    # Build output metadata lookup: param_name → output_def
    output_meta: dict[str, dict] = {}
    for output_def in getattr(func, "__stimela_outputs__", []):
        py_name = output_def["name"].replace("-", "_")
        output_meta[py_name] = output_def

    # Extract stimela metadata from Annotated type hints
    stimela_meta = _extract_stimela_meta_from_hints(func)

    hints = typing.get_type_hints(func, include_extras=True)
    mounts: dict[str, bool] = {}

    def add_mount(path: str, readwrite: bool) -> None:
        """Add a mount, upgrading ro → rw if needed."""
        mounts[path] = mounts.get(path, False) or readwrite

    for param_name, value in params.items():
        if value is None:
            continue
        hint = hints.get(param_name)
        if hint is None or not _is_path_type(hint):
            continue

        is_output = param_name in output_meta

        # Gather path_policies from output decorator and/or stimela metadata dict
        meta = stimela_meta.get(param_name, {})
        output_def = output_meta.get(param_name, {})
        base_policies = output_def.get("path_policies") or {}
        path_policies = {**base_policies, **meta.get("path_policies", {})}
        must_exist = meta.get("must_exist", output_def.get("must_exist"))
        do_mkdir = meta.get("mkdir", output_def.get("mkdir", False))
        write_parent = path_policies.get("write_parent", False)
        access_parent = path_policies.get("access_parent", False)

        paths = [value] if not isinstance(value, list) else value

        for p in paths:
            if _is_remote_upath(p):
                continue
            if not isinstance(p, Path):
                continue
            abs_path = p.resolve()
            path_str = str(abs_path)
            parent_str = str(abs_path.parent)

            if write_parent or do_mkdir:
                # Mount the parent directory rw instead of the path itself.
                # This avoids "device or resource busy" when the container
                # needs to create/overwrite the target directory.
                add_mount(parent_str, True)
            elif abs_path.is_dir():
                add_mount(path_str, is_output)
            elif abs_path.exists():
                add_mount(parent_str, is_output)
            else:
                # Path doesn't exist — mount parent
                if must_exist:
                    raise RuntimeError(f"Parameter '{param_name}': path '{abs_path}' does not exist")
                add_mount(parent_str, is_output)

            # Also mount parent if access_parent is requested
            if access_parent and not write_parent:
                add_mount(parent_str, False)

    # Eliminate redundant child mounts when parent is already mounted with >= privileges
    _prune_child_mounts(mounts)

    return mounts


def _extract_stimela_meta_from_hints(func: typing.Callable) -> dict[str, typing.Mapping]:
    """Extract stimela metadata from a function's Annotated type hints.

    Accepts both the preferred ``StimelaMeta(...)`` form and the legacy
    ``{"stimela": {...}}`` dict literal form. Legacy dicts are wrapped in a
    ``StimelaMeta`` so callers always get a Mapping.

    Returns:
        Dict mapping parameter names to their stimela metadata mappings.
    """
    result: dict[str, typing.Mapping] = {}
    hints = typing.get_type_hints(func, include_extras=True)
    for param_name, hint in hints.items():
        origin = typing.get_origin(hint)
        if origin is not typing.Annotated:
            continue
        for meta_item in typing.get_args(hint)[1:]:
            if isinstance(meta_item, StimelaMeta):
                result[param_name] = meta_item
                break
            if isinstance(meta_item, dict) and "stimela" in meta_item:
                result[param_name] = StimelaMeta.from_mapping(meta_item["stimela"])
                break
    return result


def _prune_child_mounts(mounts: dict[str, bool]) -> None:
    """Remove mounts whose parent is already mounted with equal or greater privileges."""
    to_remove = set()
    for path, rw in list(mounts.items()):
        parent = os.path.dirname(path)
        while parent != "/" and parent != path:
            if parent in mounts and mounts[parent] >= rw:
                to_remove.add(path)
                break
            parent = os.path.dirname(parent)
    for path in to_remove:
        del mounts[path]


def _is_path_type(tp: typing.Any) -> bool:
    """Check if a type hint resolves to a Path-like type.

    Handles Annotated, Optional, Union, list, and NewType wrappers.
    """
    origin = typing.get_origin(tp)

    # Annotated[X, ...] → check X
    if origin is typing.Annotated:
        return _is_path_type(typing.get_args(tp)[0])

    # Union / X | None → check non-None args
    if origin is types.UnionType or origin is typing.Union:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return any(_is_path_type(a) for a in args)

    # list[X] → check X
    if origin is list:
        args = typing.get_args(tp)
        return bool(args) and _is_path_type(args[0])

    # Path / UPath check: match pathlib hierarchy or UPath hierarchy
    if tp is Path:
        return True
    if isinstance(tp, type) and (issubclass(tp, PurePath) or issubclass(tp, UPath)):
        return True

    # NewType: has __supertype__
    if hasattr(tp, "__supertype__"):
        return _is_path_type(tp.__supertype__)

    return False


_LOCAL_PROTOCOLS = frozenset({"", "file", "local"})


def _is_remote_upath(value: typing.Any) -> bool:
    """Return True if value is a UPath with a non-local protocol."""
    protocol = getattr(value, "protocol", None)
    if protocol is None:
        return False
    if isinstance(protocol, tuple):
        protocol = protocol[0] if protocol else ""
    return protocol not in _LOCAL_PROTOCOLS


def _collect_remote_protocols(func: typing.Callable, params: dict[str, typing.Any]) -> set[str]:
    """Scan path-typed params and return the set of non-local protocols in use."""
    hints = typing.get_type_hints(func, include_extras=True)
    protocols: set[str] = set()
    for name, value in params.items():
        if value is None:
            continue
        if name in hints and not _is_path_type(hints[name]):
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if _is_remote_upath(v):
                proto = v.protocol
                if isinstance(proto, tuple):
                    proto = proto[0]
                protocols.add(proto)
    return protocols


def preflight_remote_must_exist(func: typing.Callable, params: dict[str, typing.Any]) -> None:
    """For remote UPath params whose metadata sets must_exist=True, verify they exist.

    Local paths and params without ``must_exist`` are ignored — those contracts
    are enforced elsewhere (mount logic for local paths; the user's own code
    otherwise). Raises ``typer.Exit(1)`` on a missing remote URI.
    """
    import typer

    stimela_meta = _extract_stimela_meta_from_hints(func)
    output_meta: dict[str, dict] = {}
    for output_def in getattr(func, "__stimela_outputs__", []):
        py_name = output_def["name"].replace("-", "_")
        output_meta[py_name] = output_def

    for name, value in params.items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        meta = stimela_meta.get(name, {})
        output_def = output_meta.get(name, {})
        must_exist = meta.get("must_exist", output_def.get("must_exist"))
        if not must_exist:
            continue
        for v in values:
            if not _is_remote_upath(v):
                continue
            if not v.exists():
                typer.echo(
                    f"Parameter '{name}': '{v}' does not exist",
                    err=True,
                )
                raise typer.Exit(code=1)


# Per-scheme credential mapping. Keys are normalised protocol names; values
# are the host env vars to forward when the scheme is present in the params.
_CREDENTIAL_ENV_VARS: dict[str, tuple[str, ...]] = {
    "s3": (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_ENDPOINT_URL",
    ),
    "gcs": ("GOOGLE_APPLICATION_CREDENTIALS",),
    "az": (
        "AZURE_STORAGE_ACCOUNT",
        "AZURE_STORAGE_KEY",
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_SECRET",
    ),
}

# Alternate protocol names that should share a credential group.
_PROTOCOL_ALIASES: dict[str, str] = {
    "gs": "gcs",
    "abfs": "az",
    "adl": "az",
}


def _normalise_protocol(proto: str) -> str:
    return _PROTOCOL_ALIASES.get(proto, proto)


def _build_credential_env(protocols: set[str], env: dict[str, str]) -> dict[str, str]:
    """Return host env vars to forward for the given protocol set."""
    result: dict[str, str] = {}
    seen: set[str] = set()
    for proto in protocols:
        group = _normalise_protocol(proto)
        for var in _CREDENTIAL_ENV_VARS.get(group, ()):
            if var in seen:
                continue
            seen.add(var)
            if var in env:
                result[var] = env[var]
    return result


def _build_credential_mounts(
    protocols: set[str],
    env: dict[str, str],
    home: os.PathLike[str] | str,
) -> tuple[dict[str, bool], str | None]:
    """Return read-only mounts + optional GCS key file path for the given protocols."""
    home_path = Path(home)
    mounts: dict[str, bool] = {}
    keyfile: str | None = None

    for proto in protocols:
        group = _normalise_protocol(proto)
        if group == "s3":
            # Skip ~/.aws when short-lived creds are active to avoid stale
            # profile files masking the session.
            if "AWS_SESSION_TOKEN" in env:
                continue
            aws = home_path / ".aws"
            if aws.is_dir():
                mounts[str(aws)] = False
        elif group == "gcs":
            gcloud = home_path / ".config" / "gcloud"
            if gcloud.is_dir():
                mounts[str(gcloud)] = False
            key = env.get("GOOGLE_APPLICATION_CREDENTIALS")
            if key:
                key_path = Path(key)
                if key_path.is_file():
                    mounts[str(key_path)] = False
                    keyfile = str(key_path)
        elif group == "az":
            azure = home_path / ".azure"
            if azure.is_dir():
                mounts[str(azure)] = False

    return mounts, keyfile


def _build_argv_with_native_backend() -> list[str]:
    """Copy sys.argv, replacing or appending --backend native."""
    args = list(sys.argv)

    # Replace entry point path with just the name
    args[0] = Path(args[0]).name

    # Find and replace --backend (both '--backend VALUE' and '--backend=VALUE'), or append it
    for i, arg in enumerate(args):
        if arg == "--backend" and i + 1 < len(args):
            args[i + 1] = "native"
            return args
        if arg.startswith("--backend="):
            args[i] = "--backend=native"
            return args

    args.extend(["--backend", "native"])
    return args


def _build_container_cmd(
    runtime: str,
    image: str,
    mounts: dict[str, bool],
    cwd: str,
    cli_args: list[str],
    cred_env: dict[str, str] | None = None,
    cred_mounts: dict[str, bool] | None = None,
) -> list[str]:
    """Assemble the full container execution command.

    Args:
        runtime: Container runtime (apptainer, singularity, docker, podman).
        image: Container image reference.
        mounts: Dict of mount paths → read-write flag.
        cwd: Working directory inside the container.
        cli_args: The CLI command + arguments to run inside the container.
        cred_env: Optional env vars to forward into the container (e.g. cloud creds).
        cred_mounts: Optional read-only credential mounts merged with ``mounts``.
    """
    cred_env = cred_env or {}
    cred_mounts = cred_mounts or {}
    all_mounts = {**mounts, **cred_mounts}

    if runtime in ("apptainer", "singularity"):
        cmd = [runtime, "exec", "--pwd", cwd]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["--bind", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["--env", f"{var}={value}"])
        # Add docker:// prefix for OCI image references
        if not image.endswith(".sif") and "://" not in image:
            image = f"docker://{image}"
        cmd.append(image)
    else:  # docker, podman
        # Run as current user so output files have correct ownership
        uid_gid = f"{os.getuid()}:{os.getgid()}"
        cmd = [runtime, "run", "--rm", "--user", uid_gid, "-w", cwd]
        for path, rw in sorted(all_mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["-v", f"{path}:{path}:{mode}"])
        for var, value in sorted(cred_env.items()):
            cmd.extend(["-e", f"{var}={value}"])
        cmd.append(image)

    cmd.extend(cli_args)
    return cmd
