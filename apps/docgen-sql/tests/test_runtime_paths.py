from pathlib import Path

from src.runtime_paths import get_project_root, project_path


def test_project_root_points_to_repo_root():
    root = get_project_root()

    assert (root / "src").exists()
    assert (root / "config").exists()
    assert (root / "input").exists()


def test_project_path_appends_segments():
    expected = Path(get_project_root()) / "input" / "templates"

    assert project_path("input", "templates") == expected
