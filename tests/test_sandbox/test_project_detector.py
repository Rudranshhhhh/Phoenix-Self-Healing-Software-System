import json

from agent.sandbox.project_detector import detect_project


def test_detects_node_project_with_package_scripts(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    plan = detect_project(tmp_path)

    assert plan.language == "javascript"
    assert plan.install_command == ("npm", "ci")
    assert plan.lint_command == ("npm", "run", "lint")
    assert plan.test_command == ("npm", "test")


def test_defaults_to_python_without_node_manifest(tmp_path):
    plan = detect_project(tmp_path)

    assert plan.language == "python"
    assert plan.install_command is None
    assert plan.test_command is None
