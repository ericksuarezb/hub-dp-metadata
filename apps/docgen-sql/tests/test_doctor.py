from src.doctor import inspect_project


def test_doctor_report_has_project_root():
    report = inspect_project()

    assert report["project_root"]
    assert isinstance(report["checks"], list)
    assert isinstance(report["dependencies"], list)
    assert "recommendation" in report
