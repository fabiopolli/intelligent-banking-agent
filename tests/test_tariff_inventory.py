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


def test_published_tariffs_are_reviewed_and_cover_demo_categories() -> None:
    entries = TariffCatalogLoader().load_entries()["entries"]

    assert len(entries) >= 25
    assert all(entry["reviewed_at"] for entry in entries if entry["status"] == "published")
    assert {entry["category"] for entry in entries} >= {
        "saque", "transferencias", "cartoes", "cheques", "investimentos"
    }
    assert any(entry.get("amount") == "11.10" and "TED" in entry["service_name"] for entry in entries)


def test_auxiliary_catalog_populates_packages_items_rules_and_links() -> None:
    catalog = TariffCatalogLoader().load_auxiliary()

    assert len(catalog["packages"]) == 50
    assert len(catalog["package_items"]) == 78
    assert len(catalog["rules"]) == 56
    assert len(catalog["entry_rule_links"]) == 10
    assert all(item["status"] == "published" and item["reviewed_at"] for item in catalog["packages"])
    assert all(item["status"] == "published" and item["reviewed_at"] for item in catalog["rules"])


def test_tariff_reconciliation_accounts_for_every_pdf_page_and_catalog_record() -> None:
    reconciliation = TariffCatalogLoader().load_reconciliation()

    assert len(reconciliation["pages"]) == 25
    assert all(page["status"] in {"reviewed", "complete_with_conflicts"} for page in reconciliation["pages"])
    assert len(reconciliation["conflicts"]) == 2
    assert all(conflict["status"] == "review_required" for conflict in reconciliation["conflicts"])
