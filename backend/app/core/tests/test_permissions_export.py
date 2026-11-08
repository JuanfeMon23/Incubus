"""El contrato `permissions.json` del frontend coincide con el catalogo del backend."""

from app.core import permissions_export as export
from app.core.leo import catalog


def test_committed_contract_matches_catalog() -> None:
    assert export.CONTRACT_PATH.exists(), export.MISMATCH_MESSAGE
    assert (
        export.CONTRACT_PATH.read_bytes().decode("utf-8") == export.render_contract()
    ), export.MISMATCH_MESSAGE


def test_contract_has_every_tag_and_flags_events() -> None:
    contract = export.build_contract()
    actions = [action for module in contract["modules"] for action in module["actions"]]
    assert {action["tag"] for action in actions} == set(catalog.tags)
    not_assignable = {action["tag"] for action in actions if not action["assignable"]}
    assert not_assignable == {"incubus.settings.update"}


def test_check_reports_mismatch(monkeypatch, tmp_path, capsys) -> None:
    stale = tmp_path / "permissions.json"
    stale.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(export, "CONTRACT_PATH", stale)
    assert export.main(["--check"]) == 1
    assert export.MISMATCH_MESSAGE in capsys.readouterr().out
    assert export.main([]) == 0
    assert export.main(["--check"]) == 0
