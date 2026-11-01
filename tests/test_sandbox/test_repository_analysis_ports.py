from agent.worker.repository_analysis import _candidate_ports


def test_existing_dockerfile_uses_declared_ports(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.11\nEXPOSE 3000\nEXPOSE 8080\n", encoding="utf-8")

    assert _candidate_ports(tmp_path, dockerfile) == [3000, 8080]


def test_existing_dockerfile_without_expose_uses_python_defaults(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.11\n", encoding="utf-8")

    assert _candidate_ports(tmp_path, dockerfile) == [8000, 8080, 5000]


def test_existing_dockerfile_includes_command_port_when_expose_differs(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        'FROM python:3.11\nEXPOSE 8000\nCMD ["uvicorn", "app:app", "--port", "8080"]\n',
        encoding="utf-8",
    )

    assert _candidate_ports(tmp_path, dockerfile) == [8000, 8080]
