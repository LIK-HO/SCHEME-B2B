import json
from pathlib import Path

from scheme_b2b.cli import main


def test_check_returns_latest_fns_state(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    xml = (
        '<EGRUL ДатаВыг="2026-09-19">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА">'
        '<СвСтатус НаимСтатусЮЛ="Действующее"/></СвЮЛ></EGRUL>'
    )
    path = tmp_path / "fns.xml"
    path.write_text(xml, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["scheme-b2b", "import-fns", str(path)])
    assert main() == 0
    monkeypatch.setattr("sys.argv", ["scheme-b2b", "check", "7707083893", "1027700132195"])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["ok"] is True
