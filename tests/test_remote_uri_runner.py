"""Tests for remote-URI-aware runner behaviour.

Subsequent tasks (6, 7, 9, 10, 11) append additional test functions here.
"""

from typing import Annotated

import fsspec
import pytest
import typer
from upath import UPath

from hip_cargo.utils.introspector import MS, URI, Directory, File
from hip_cargo.utils.metadata import StimelaMeta
from hip_cargo.utils.runner import (
    _build_container_cmd,
    _build_credential_env,
    _build_credential_mounts,
    _collect_remote_protocols,
    _is_path_type,
    _is_remote_upath,
    _resolve_mounts,
    preflight_remote_must_exist,
)


def test_is_path_type_detects_upath_newtypes():
    assert _is_path_type(File) is True
    assert _is_path_type(Directory) is True
    assert _is_path_type(MS) is True
    assert _is_path_type(URI) is True


def test_is_path_type_detects_list_of_upath_newtype():
    assert _is_path_type(list[File]) is True


def test_is_remote_upath_local():
    assert _is_remote_upath(UPath("/tmp/x")) is False


def test_is_remote_upath_memory():
    assert _is_remote_upath(UPath("memory:///scratch/x")) is True


def test_is_remote_upath_s3():
    assert _is_remote_upath(UPath("s3://bkt/k")) is True


def test_collect_remote_protocols_mixed():
    def fn(
        a: Annotated[File, typer.Option()] = UPath("/tmp/a"),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/b"),  # noqa: B008
        c: Annotated[File, typer.Option()] = UPath("memory:///c"),  # noqa: B008
    ) -> None:
        pass

    params = {
        "a": UPath("/tmp/a"),
        "b": UPath("s3://bkt/b"),
        "c": UPath("memory:///c"),
    }
    protocols = _collect_remote_protocols(fn, params)
    assert protocols == {"s3", "memory"}


def test_collect_remote_protocols_all_local():
    def fn(a: Annotated[File, typer.Option()] = UPath("/tmp/a")) -> None:  # noqa: B008
        pass

    assert _collect_remote_protocols(fn, {"a": UPath("/tmp/a")}) == set()


def test_collect_remote_protocols_none_value():
    def fn(a: Annotated[File | None, typer.Option()] = None) -> None:
        pass

    assert _collect_remote_protocols(fn, {"a": None}) == set()


def test_collect_remote_protocols_list_of_paths():
    def fn(xs: Annotated[list[File], typer.Option()] = ()) -> None:  # noqa: B008
        pass

    params = {
        "xs": [
            UPath("/tmp/a"),
            UPath("s3://bkt/x"),
            UPath("memory:///c"),
        ]
    }
    assert _collect_remote_protocols(fn, params) == {"s3", "memory"}


def test_resolve_mounts_skips_remote_upaths(tmp_path):
    local = tmp_path / "local.fits"
    local.write_bytes(b"data")

    def fn(
        a: Annotated[File, typer.Option()] = UPath(str(local)),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/k"),  # noqa: B008
    ) -> None:
        pass

    params = {"a": UPath(str(local)), "b": UPath("s3://bkt/k")}
    mounts = _resolve_mounts(fn, params)

    # Remote param contributes nothing.
    assert not any("s3" in p or "bkt" in p for p in mounts)
    # Local param still produces a mount.
    assert any(str(tmp_path) in p for p in mounts)


def test_preflight_passes_for_existing_remote_upath():
    fs = fsspec.filesystem("memory")
    with fs.open("/present.bin", "wb") as f:
        f.write(b"x")

    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///present.bin"
        ),
    ) -> None:
        pass

    preflight_remote_must_exist(fn, {"x": UPath("memory:///present.bin")})


def test_preflight_fails_for_missing_remote_upath():
    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///absent.bin"
        ),
    ) -> None:
        pass

    with pytest.raises(typer.Exit):
        preflight_remote_must_exist(fn, {"x": UPath("memory:///absent.bin")})


def test_preflight_ignores_local_paths(tmp_path):
    missing = tmp_path / "does-not-exist.bin"

    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            str(missing)
        ),
    ) -> None:
        pass

    # Local paths are not pre-flighted here — mount logic owns that contract.
    preflight_remote_must_exist(fn, {"x": UPath(str(missing))})


def test_preflight_ignores_params_without_must_exist():
    def fn(
        x: Annotated[File, typer.Option()] = UPath("memory:///nope.bin"),  # noqa: B008
    ) -> None:
        pass

    # No StimelaMeta(must_exist=True) → skip.
    preflight_remote_must_exist(fn, {"x": UPath("memory:///nope.bin")})


def test_credential_env_s3_when_vars_present():
    env = {
        "AWS_ACCESS_KEY_ID": "k",
        "AWS_SECRET_ACCESS_KEY": "s",
        "AWS_REGION": "eu-west-1",
        "UNRELATED": "ignore",
    }
    result = _build_credential_env({"s3"}, env)
    assert result["AWS_ACCESS_KEY_ID"] == "k"
    assert result["AWS_SECRET_ACCESS_KEY"] == "s"
    assert result["AWS_REGION"] == "eu-west-1"
    assert "UNRELATED" not in result


def test_credential_env_skips_unset_vars():
    result = _build_credential_env({"s3"}, {"AWS_ACCESS_KEY_ID": "k"})
    assert result == {"AWS_ACCESS_KEY_ID": "k"}


def test_credential_env_gcs_includes_app_creds():
    env = {"GOOGLE_APPLICATION_CREDENTIALS": "/home/u/key.json"}
    result = _build_credential_env({"gcs"}, env)
    assert result["GOOGLE_APPLICATION_CREDENTIALS"] == "/home/u/key.json"


def test_credential_env_azure():
    env = {"AZURE_STORAGE_ACCOUNT": "acct", "AZURE_STORAGE_KEY": "k"}
    result = _build_credential_env({"az"}, env)
    assert result["AZURE_STORAGE_ACCOUNT"] == "acct"
    assert result["AZURE_STORAGE_KEY"] == "k"


def test_credential_mounts_s3(tmp_path):
    home = tmp_path / "home"
    aws = home / ".aws"
    aws.mkdir(parents=True)
    (aws / "credentials").write_text("[default]\n")

    mounts, keyfile = _build_credential_mounts({"s3"}, env={}, home=home)
    assert str(aws) in mounts
    assert keyfile is None


def test_credential_mounts_s3_skipped_with_session_token(tmp_path):
    home = tmp_path / "home"
    aws = home / ".aws"
    aws.mkdir(parents=True)

    mounts, _ = _build_credential_mounts({"s3"}, env={"AWS_SESSION_TOKEN": "temp"}, home=home)
    assert str(aws) not in mounts


def test_credential_mounts_gcs_binds_key_file(tmp_path):
    home = tmp_path / "home"
    key = tmp_path / "service-account.json"
    key.write_text("{}")

    mounts, keyfile = _build_credential_mounts(
        {"gcs"},
        env={"GOOGLE_APPLICATION_CREDENTIALS": str(key)},
        home=home,
    )
    assert str(key) in mounts
    assert keyfile == str(key)


def test_credential_mounts_gcs_binds_config_dir(tmp_path):
    home = tmp_path / "home"
    gcloud = home / ".config" / "gcloud"
    gcloud.mkdir(parents=True)

    mounts, _ = _build_credential_mounts({"gcs"}, env={}, home=home)
    assert str(gcloud) in mounts


def test_credential_mounts_azure(tmp_path):
    home = tmp_path / "home"
    azure = home / ".azure"
    azure.mkdir(parents=True)

    mounts, _ = _build_credential_mounts({"az"}, env={}, home=home)
    assert str(azure) in mounts


def test_build_container_cmd_docker_forwards_env_and_mounts():
    cmd = _build_container_cmd(
        runtime="docker",
        image="ghcr.io/u/r:tag",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo", "some-cmd"],
        cred_env={"AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s"},
        cred_mounts={"/home/u/.aws": False},
    )
    assert "-e" in cmd
    assert "AWS_ACCESS_KEY_ID=k" in cmd
    assert "AWS_SECRET_ACCESS_KEY=s" in cmd
    assert "/home/u/.aws:/home/u/.aws:ro" in cmd


def test_build_container_cmd_apptainer_forwards_env_and_mounts():
    cmd = _build_container_cmd(
        runtime="apptainer",
        image="ghcr.io/u/r:tag",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo", "some-cmd"],
        cred_env={"AWS_ACCESS_KEY_ID": "k"},
        cred_mounts={"/home/u/.aws": False},
    )
    assert "--env" in cmd
    assert "AWS_ACCESS_KEY_ID=k" in cmd
    assert any("/home/u/.aws:/home/u/.aws:ro" in arg for arg in cmd)


def test_build_container_cmd_no_creds_keeps_existing_output():
    cmd = _build_container_cmd(
        runtime="docker",
        image="img",
        mounts={"/data": True},
        cwd="/data",
        cli_args=["hip-cargo"],
        cred_env={},
        cred_mounts={},
    )
    # No credential env flags when nothing to forward.
    assert not any(v.startswith("AWS_") for v in cmd)
