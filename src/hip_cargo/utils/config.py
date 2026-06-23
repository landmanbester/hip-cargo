"""Read container image from installed package metadata."""

import importlib


def get_container_image(package_name: str, package_import_name: str | None = None) -> str | None:
    """Return the container image registered in a package's _container_image module.

    Dynamically imports ``<package>._container_image`` and reads the
    ``CONTAINER_IMAGE`` constant. This works from any directory because it
    reads from the installed package, not from ``pyproject.toml``.

    Args:
        package_name:
            The distribution name of the package (e.g. 'pfb-imaging').
            By default hyphens are converted to underscores to determine the name of the module to to import.
        package_import_name:
            The name of the module to import (e.g. 'pfb_imaging').
            If not provided, it is derived from `package_name` by replacing hyphens with underscores.
    Returns:
        The full container image string (including tag), or None if the
        package is not installed or has no ``_container_image`` module.
    """
    if package_import_name is not None:
        pkg = package_import_name
    else:
        pkg = package_name.replace("-", "_")
    module_name = f"{pkg}._container_image"
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, "CONTAINER_IMAGE", None)
    except ModuleNotFoundError as exc:
        if exc.name and module_name.startswith(exc.name):
            # The package or its _container_image module is not installed
            return None
        raise


def _load_container_image_module(import_name: str):
    """Import ``<import_name>._container_image`` or return None if absent.

    Mirrors the ModuleNotFoundError discrimination in get_container_image:
    a missing package/module returns None, while an unrelated import failure
    inside the module propagates.
    """
    module_name = f"{import_name}._container_image"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and module_name.startswith(exc.name):
            return None
        raise


def get_container_gpu(import_name: str) -> bool | str:
    """Return a package's declared GPU passthrough setting.

    Reads the ``GPU`` constant from ``<import_name>._container_image``.

    Args:
        import_name: Python import name of the package (e.g. 'kremetart').

    Returns:
        The ``GPU`` value (True/False or a string spec), or False if the
        package declares none.
    """
    mod = _load_container_image_module(import_name)
    if mod is None:
        return False
    return getattr(mod, "GPU", False)


def get_container_run_args(import_name: str, runtime: str) -> list[str]:
    """Return a package's declared extra run-args for a container runtime.

    Reads the ``RUN_ARGS_<RUNTIME>`` constant (e.g. ``RUN_ARGS_APPTAINER``)
    from ``<import_name>._container_image``.

    Args:
        import_name: Python import name of the package.
        runtime: Container runtime name (docker/podman/apptainer/singularity).

    Returns:
        A list of extra arguments, or an empty list if none are declared.
    """
    mod = _load_container_image_module(import_name)
    if mod is None:
        return []
    return list(getattr(mod, f"RUN_ARGS_{runtime.upper()}", []))
