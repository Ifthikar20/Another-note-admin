"""docs/ADMIN_API_CONTRACT.md's endpoint table and docs/admin-api.schema.json match the code."""

from __future__ import annotations

from . import contract_doc


def test_the_contract_doc_and_its_schema_are_current(capsys):
    assert contract_doc.main(["--check"]) == 0, capsys.readouterr().out
