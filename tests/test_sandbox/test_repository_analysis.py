import json

from agent.worker.repository_analysis import _generated_dockerfile


def test_generated_node_dockerfile_uses_vite_dev_server(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite", "build": "vite build"}}),
        encoding="utf-8",
    )

    dockerfile = _generated_dockerfile(tmp_path)

    assert "FROM node:20-alpine" in dockerfile
    assert 'npm", "run", "dev"' in dockerfile
    assert "--host" in dockerfile


def test_generated_python_dockerfile_uses_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    dockerfile = _generated_dockerfile(tmp_path)

    assert "pip install --no-cache-dir ." in dockerfile
    assert "uvicorn app.main:app" in dockerfile
