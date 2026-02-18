from hip_cargo.utils.decorators import stimela_cab


@stimela_cab(
    name="onboard",
    info="Print setup instructions for CI/CD, PyPI publishing, and GitHub configuration.",
)
def onboard():
    """
    Print setup instructions for CI/CD, PyPI publishing, and GitHub configuration.
    """
    # Lazy import the core implementation
    from <PACKAGE_NAME>.core.onboard import onboard as onboard_core  # noqa: E402

    onboard_core()
