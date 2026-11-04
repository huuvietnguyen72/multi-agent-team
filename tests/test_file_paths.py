"""write_files bỏ phần đầu đường dẫn mà model chép lại từ prompt."""
import pytest

from tools.file_tools import write_files


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("given", ["app.js", "./app.js", "frontend/app.js", "{out}/frontend/app.js"])
def test_echoed_prefixes_land_in_role_dir(out, given):
    write_files("frontend", [{"path": given.format(out=out), "content": "x"}])
    assert (out / "frontend" / "app.js").read_text() == "x"
    assert [p for p in out.rglob("app.js")] == [out / "frontend" / "app.js"]


def test_outside_path_still_refused(out):
    with pytest.raises(ValueError):
        write_files("frontend", [{"path": "../backend/x.java", "content": "x"}])
