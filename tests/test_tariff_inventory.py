import json

import pytest

from app.services.knowledge.tariff_catalog import TariffCatalogLoader


def test_tariff_inventory_covers_all_pdf_pages_and_sections() -> None:
    inventory = TariffCatalogLoader().load_inventory()

    assert inventory["page_count"] == 25
    assert [page["page_number"] for page in inventory["pages"]] == list(range(1, 26))
    assert {page["section_code"] for page in inventory["pages"]} == {
        "front_matter",
        "packages",
        "priority_services",
        "cards_checks_transfers",
        "credit_fx_investments",
        "legends",
    }
    assert all(page["review_status"] == "review_required" for page in inventory["pages"])


def test_tariff_inventory_rejects_missing_pages(tmp_path) -> None:  # noqa: ANN001
    inventory = TariffCatalogLoader().load_inventory()
    inventory["pages"].pop()
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly 25 pages"):
        TariffCatalogLoader(path).load_inventory()
