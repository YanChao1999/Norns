from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.sandbox.providers import (
    DirectoryCopySandboxProvider,
    DockerSandboxProvider,
    GvisorSandboxProvider,
    MicroVmSandboxProvider,
    NoneSandboxProvider,
    docker_run_command,
    run_in_sandbox,
)
from backend.app.sandbox.runtime import get_sandbox_provider, prepare_sandbox, serialize_sandbox
from backend.app.workspace import Workspace


def test_directory_copy_prepares_isolated_tree(tmp_path: Path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "readme.txt").write_text("hello", encoding="utf-8")
    (source / "node_modules").mkdir()
    (source / "node_modules" / "pkg").write_text("skip", encoding="utf-8")
    root = tmp_path / "sandboxes"
    provider = DirectoryCopySandboxProvider(root=root)
    handle = provider.prepare(
        run_id="run-1",
        card_id="card-1",
        board_id="board-1",
        source=Workspace(path=str(source), git_url="", source="test"),
    )
    assert handle is not None
    assert handle.backend == "directory"
    assert Path(handle.path).is_dir()
    assert (Path(handle.path) / "readme.txt").read_text(encoding="utf-8") == "hello"
    assert not (Path(handle.path) / "node_modules").exists()
    marker = Path(handle.path) / "agent-write.txt"
    marker.write_text("mutated", encoding="utf-8")
    assert not (source / "agent-write.txt").exists()
    provider.cleanup(handle)
    assert not Path(handle.path).exists()


def test_directory_copy_skips_without_local_path(tmp_path: Path):
    provider = DirectoryCopySandboxProvider(root=tmp_path / "sandboxes")
    assert (
        provider.prepare(
            run_id="run-1",
            card_id="card-1",
            board_id="board-1",
            source=Workspace(path="", git_url="https://github.com/acme/app", source="test"),
        )
        is None
    )


def test_none_and_microvm_providers():
    source = Workspace(path="/tmp/x", git_url="", source="test")
    assert NoneSandboxProvider().prepare(run_id="r", card_id="c", board_id="b", source=source) is None
    assert MicroVmSandboxProvider().prepare(run_id="r", card_id="c", board_id="b", source=source) is None
    assert GvisorSandboxProvider().prepare(run_id="r", card_id="c", board_id="b", source=source) is None


def test_get_sandbox_provider_from_settings(tmp_path: Path):
    assert get_sandbox_provider(SimpleNamespace(sandbox_backend="none")).name == "none"
    assert get_sandbox_provider(SimpleNamespace(sandbox_backend="microvm")).name == "microvm"
    assert get_sandbox_provider(SimpleNamespace(sandbox_backend="gvisor")).name == "gvisor"
    assert get_sandbox_provider(SimpleNamespace(sandbox_backend="docker", sandbox_image="alpine:3")).name == "docker"
    provider = get_sandbox_provider(SimpleNamespace(sandbox_backend="directory", sandbox_root=str(tmp_path)))
    assert provider.name == "directory"


def test_prepare_sandbox_and_serialize(tmp_path: Path):
    source_dir = tmp_path / "ws"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("a", encoding="utf-8")
    settings = SimpleNamespace(sandbox_backend="directory", sandbox_root=str(tmp_path / "sandboxes"))
    source = Workspace(path=str(source_dir), git_url="https://github.com/acme/app", source="test")
    provider, handle = prepare_sandbox(settings, run_id="run-9", card_id="card-9", board_id="board-9", source=source)
    assert provider.name == "directory"
    assert handle is not None
    payload = serialize_sandbox(handle, source=source)
    assert payload["backend"] == "directory"
    assert payload["path"] == handle.path
    assert payload["source_path"] == str(source_dir.resolve())
    provider.cleanup(handle)


def test_docker_provider_falls_back_when_docker_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr("backend.app.sandbox.providers.docker_executable", lambda: None)
    provider = DockerSandboxProvider(root=tmp_path / "sandboxes", docker_bin=None)
    # Force _docker to miss even if docker_bin was set somehow
    provider._docker_bin = None
    handle = provider.prepare(
        run_id="run-d",
        card_id="card-d",
        board_id="board-d",
        source=Workspace(path=str(source), git_url="", source="test"),
    )
    assert handle is not None
    assert handle.backend == "directory"
    assert handle.metadata and handle.metadata.get("fallback_from") == "docker"
    assert handle.metadata.get("fallback_reason") == "docker_unavailable"
    provider.cleanup(handle)


def test_docker_run_command_is_hardened(tmp_path: Path):
    host = tmp_path / "sandboxes" / "copy"
    host.mkdir(parents=True)
    cmd = docker_run_command(
        "/usr/bin/docker",
        image="python:3.12-slim",
        host_path=str(host),
        container_name="norns-sb-test",
    )
    assert cmd[0:3] == ["/usr/bin/docker", "run", "-d"]
    assert "--read-only" in cmd
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges:true" in cmd
    mount = cmd[cmd.index("--mount") + 1]
    assert mount.startswith("type=bind,source=")
    assert mount.endswith(",target=/workspace")
    assert str(host.resolve()) in mount
    # Only one host bind mount argument — no docker.sock / home / root mounts.
    assert sum(1 for part in cmd if isinstance(part, str) and part.startswith("type=bind,")) == 1
    assert "-v" not in cmd
    assert any(part.startswith("/tmp:") for part in cmd)
    assert "sleep" in cmd and "infinity" in cmd


def test_docker_provider_starts_container(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(list(command))
        if command[1] == "run":
            return SimpleNamespace(stdout="cid123\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr("backend.app.sandbox.providers.subprocess.run", fake_run)
    provider = DockerSandboxProvider(
        root=tmp_path / "sandboxes",
        image="public.ecr.aws/docker/library/python:3.12-slim",
        docker_bin="/usr/bin/docker",
    )
    handle = provider.prepare(
        run_id="run-docker",
        card_id="card-d",
        board_id="board-d",
        source=Workspace(path=str(source), git_url="", source="test"),
    )
    assert handle is not None
    assert handle.backend == "docker"
    assert handle.metadata is not None
    assert handle.metadata["container_id"] == "cid123"
    assert handle.metadata["workdir"] == "/workspace"
    assert handle.metadata["hardened"] is True
    assert "cap-drop-all" in handle.metadata["policy"]
    run_cmd = next(cmd for cmd in calls if cmd[1] == "run")
    assert "--read-only" in run_cmd
    assert "--cap-drop" in run_cmd
    assert any(part.startswith("type=bind,source=") for part in run_cmd)
    provider.cleanup(handle)
    assert any(cmd[:3] == ["/usr/bin/docker", "rm", "-f"] for cmd in calls)


def test_run_in_sandbox_uses_docker_exec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.app.sandbox.base import SandboxHandle

    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        seen.append(list(command))
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr("backend.app.sandbox.providers.docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr("backend.app.sandbox.providers.subprocess.run", fake_run)
    handle = SandboxHandle(
        path=str(tmp_path),
        backend="docker",
        source_path=str(tmp_path),
        metadata={"container_id": "abc", "workdir": "/workspace"},
    )
    result = run_in_sandbox(handle, ["pytest", "-q"])
    assert result.returncode == 0
    assert seen[0] == ["/usr/bin/docker", "exec", "-w", "/workspace", "abc", "pytest", "-q"]
