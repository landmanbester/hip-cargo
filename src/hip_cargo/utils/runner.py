"""Container fallback execution for hip-cargo CLI commands."""

import os
import shutil
import subprocess
import sys
import types
import typing
from pathlib import Path

CONTAINER_RUNTIMES = ["apptainer", "singularity", "docker", "podman"]


def run_in_container(
    func: typing.Callable,
    params: dict[str, typing.Any],
    backend: str = "auto",
    always_pull_images: bool = False,
) -> None:
    """Run a CLI command inside a container, mounting required volumes.

    Args:
        func: The decorated CLI function (has __stimela_cab_config__ and __stimela_outputs__).
        params: Parameter name → value dict (excludes backend).
        backend: Container runtime to use, or "auto" to detect.
        always_pull_images: Force re-pull of the container image even if cached locally.
    """
    cab_config = getattr(func, "__stimela_cab_config__", {})
    image = cab_config.get("image")
    if not image:
        raise RuntimeError(
            f"Cannot fall back to container for '{cab_config.get('name', '?')}': "
            f"no container image specified in @stimela_cab decorator."
        )

    runtime = _detect_runtime(backend)
    mounts = _resolve_mounts(func, params)
    cwd = os.getcwd()
    # Ensure cwd is mounted read-write
    mounts[cwd] = True
    cli_args = _build_argv_with_native_backend()

    if always_pull_images:
        _pull_image(runtime, image)

    cmd = _build_container_cmd(runtime, image, mounts, cwd, cli_args)

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

    raise RuntimeError(
        "No container runtime found. Install one of: "
        + ", ".join(CONTAINER_RUNTIMES)
        + "\nOr install the full package dependencies to run natively."
    )


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
        path_policies = output_def.get("path_policies", {})
        path_policies.update(meta.get("path_policies", {}))
        must_exist = meta.get("must_exist", output_def.get("must_exist"))
        do_mkdir = meta.get("mkdir", output_def.get("mkdir", False))
        write_parent = path_policies.get("write_parent", False)
        access_parent = path_policies.get("access_parent", False)

        paths = [value] if not isinstance(value, list) else value

        for p in paths:
            if not isinstance(p, Path):
                continue
            abs_path = p.resolve()
            path_str = str(abs_path).rstrip("/")
            parent_str = str(abs_path.parent).rstrip("/")

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


def _extract_stimela_meta_from_hints(func: typing.Callable) -> dict[str, dict]:
    """Extract {"stimela": {...}} metadata from function's Annotated type hints.

    Returns:
        Dict mapping parameter names to their stimela metadata dicts.
    """
    result: dict[str, dict] = {}
    hints = typing.get_type_hints(func, include_extras=True)
    for param_name, hint in hints.items():
        origin = typing.get_origin(hint)
        if origin is not typing.Annotated:
            continue
        for meta_item in typing.get_args(hint)[1:]:
            if isinstance(meta_item, dict) and "stimela" in meta_item:
                result[param_name] = meta_item["stimela"]
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

    # Direct Path check
    if tp is Path:
        return True
    if isinstance(tp, type) and issubclass(tp, Path):
        return True

    # NewType: has __supertype__
    if hasattr(tp, "__supertype__"):
        return _is_path_type(tp.__supertype__)

    return False


def _build_argv_with_native_backend() -> list[str]:
    """Copy sys.argv, replacing or appending --backend native."""
    args = list(sys.argv)

    # Replace entry point path with just the name
    args[0] = Path(args[0]).name

    # Find and replace --backend, or append it
    for i, arg in enumerate(args):
        if arg == "--backend" and i + 1 < len(args):
            args[i + 1] = "native"
            return args

    args.extend(["--backend", "native"])
    return args


def _build_container_cmd(
    runtime: str,
    image: str,
    mounts: dict[str, bool],
    cwd: str,
    cli_args: list[str],
) -> list[str]:
    """Assemble the full container execution command.

    Args:
        runtime: Container runtime (apptainer, singularity, docker, podman).
        image: Container image reference.
        mounts: Dict of mount paths → read-write flag.
        cwd: Working directory inside the container.
        cli_args: The CLI command + arguments to run inside the container.
    """
    if runtime in ("apptainer", "singularity"):
        cmd = [runtime, "exec", "--pwd", cwd]
        for path, rw in sorted(mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["--bind", f"{path}:{path}:{mode}"])
        # Add docker:// prefix for OCI image references
        if not image.endswith(".sif") and "://" not in image:
            image = f"docker://{image}"
        cmd.append(image)
    else:  # docker, podman
        # Run as current user so output files have correct ownership
        uid_gid = f"{os.getuid()}:{os.getgid()}"
        cmd = [runtime, "run", "--rm", "--user", uid_gid, "-w", cwd]
        for path, rw in sorted(mounts.items()):
            mode = "rw" if rw else "ro"
            cmd.extend(["-v", f"{path}:{path}:{mode}"])
        cmd.append(image)

    cmd.extend(cli_args)
    return cmd
