"""Opt-in live GPU smoke test for the container fallback.

Runs only when HIP_CARGO_LIVE_GPU is set; excluded from required CI. Confirms
that a command assembled with our GPU flags actually sees the GPU inside a
container. Override the test image with HIP_CARGO_LIVE_GPU_IMAGE.
"""

import os
import subprocess

import pytest

from hip_cargo.utils.runner import (
    _build_container_cmd,
    _detect_runtime,
    _gpu_args,
    _resolve_gpu_request,
)

LIVE = os.environ.get("HIP_CARGO_LIVE_GPU")
IMAGE = os.environ.get("HIP_CARGO_LIVE_GPU_IMAGE", "nvidia/cuda:13.0.0-runtime-ubuntu24.04")


@pytest.mark.skipif(not LIVE, reason="set HIP_CARGO_LIVE_GPU=1 to run the live GPU test")
def test_gpu_visible_in_container():
    try:
        runtime = _detect_runtime("auto")
    except RuntimeError:
        pytest.skip("no container runtime available")

    spec = _resolve_gpu_request("auto", runtime)
    if spec is None:
        pytest.skip("no GPU / container toolkit detected on host")

    gpu_args, gpu_env = _gpu_args(runtime, spec)
    cmd = _build_container_cmd(
        runtime,
        IMAGE,
        {},
        "/",
        ["nvidia-smi", "-L"],
        cred_env=gpu_env,
        gpu_args=gpu_args,
    )

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"command failed:\n{' '.join(cmd)}\n{result.stderr}"
    assert "GPU" in result.stdout, f"no GPU listed in output:\n{result.stdout}"
