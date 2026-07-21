from __future__ import annotations

import json
from pathlib import Path


TARIFF_INVENTORY_PATH = Path("knowledge/catalog/tariff_inventory.json")
TARIFF_ENTRIES_PATH = Path("knowledge/catalog/tariff_entries.json")
TARIFF_AUXILIARY_PATH = Path("knowledge/catalog/tariff_auxiliary.json")
TARIFF_RECONCILIATION_PATH = Path("knowledge/catalog/tariff_reconciliation.json")


class TariffCatalogLoader:
    def __init__(
        self,
        inventory_path: Path = TARIFF_INVENTORY_PATH,
        entries_path: Path = TARIFF_ENTRIES_PATH,
        auxiliary_path: Path = TARIFF_AUXILIARY_PATH,
        reconciliation_path: Path = TARIFF_RECONCILIATION_PATH,
    ) -> None:
        self._inventory_path = inventory_path
        self._entries_path = entries_path
        self._auxiliary_path = auxiliary_path
        self._reconciliation_path = reconciliation_path

    def load_reconciliation(self) -> dict:
        payload = json.loads(self._reconciliation_path.read_text(encoding="utf-8"))
        pages = payload.get("pages", [])
        if payload.get("page_count") != 25 or [item.get("page_number") for item in pages] != list(range(1, 26)):
            raise ValueError("Tariff reconciliation must cover all 25 contiguous PDF pages.")

        entries = self.load_entries()["entries"]
        auxiliary = self.load_auxiliary()
        package_page = {item["package_id"]: item["page_number"] for item in auxiliary["packages"]}
        actual = {
            page: {
                "tariff_records": sum(item["page_number"] == page for item in entries),
                "package_records": sum(item["page_number"] == page for item in auxiliary["packages"]),
                "package_item_records": sum(package_page[item["package_id"]] == page for item in auxiliary["package_items"]),
                "rule_records": sum(item["page_number"] == page for item in auxiliary["rules"]),
            }
            for page in range(1, 26)
        }
        for page in pages:
            counts = actual[page["page_number"]]
            if any(page[field] != counts[field] for field in counts):
                raise ValueError(f"Tariff reconciliation count mismatch on page {page['page_number']}.")
            if page.get("status") not in {"reviewed", "complete_with_conflicts"}:
                raise ValueError(f"Tariff page {page['page_number']} is not fully reconciled.")
        if any(item.get("status") != "review_required" for item in payload.get("conflicts", [])):
            raise ValueError("Tariff conflicts must remain blocked for review.")
        return payload

    def load_inventory(self) -> dict:
        payload = json.loads(self._inventory_path.read_text(encoding="utf-8"))
        self._validate_inventory(payload)
        return payload

    def load_auxiliary(self) -> dict:
        payload = json.loads(self._auxiliary_path.read_text(encoding="utf-8"))
        for rule in payload.get("rules", []):
            if rule.get("page_number") == 23:
                rule["rule_code"] = f"NOTE-{rule['rule_code']}"
        package_ids = {item["package_id"] for item in payload.get("packages", [])}
        rule_ids = {item["rule_id"] for item in payload.get("rules", [])}
        tariff_ids = {item["tariff_id"] for item in self.load_entries()["entries"]}
        if not package_ids or not rule_ids:
            raise ValueError("Tariff packages and rules cannot be empty.")
        if any(item["package_id"] not in package_ids for item in payload.get("package_items", [])):
            raise ValueError("Every package item must reference a known package.")
        for link in payload.get("entry_rule_links", []):
            if link["tariff_id"] not in tariff_ids or link["rule_id"] not in rule_ids:
                raise ValueError("Every tariff rule link must resolve both references.")
        return payload

    def load_entries(self) -> dict:
        payload = json.loads(self._entries_path.read_text(encoding="utf-8"))
        entries = payload.get("entries", [])
        identifiers = [entry.get("tariff_id") for entry in entries]
        if not entries or any(not identifier for identifier in identifiers):
            raise ValueError("Tariff entries require stable identifiers.")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Tariff identifiers must be unique.")
        inventory = self.load_inventory()
        valid_sections = {section["code"] for section in inventory["sections"]}
        for entry in entries:
            if entry.get("section_code") not in valid_sections:
                raise ValueError(f"Unknown tariff section: {entry.get('section_code')}")
            if not 1 <= int(entry.get("page_number", 0)) <= 25:
                raise ValueError(f"Invalid tariff page: {entry.get('page_number')}")
            if entry.get("status") == "published" and not entry.get("reviewed_at"):
                raise ValueError(f"Published tariff {entry['tariff_id']} requires review date.")
        return payload

    def _validate_inventory(self, payload: dict) -> None:
        pages = payload.get("pages", [])
        sections = payload.get("sections", [])
        if payload.get("page_count") != 25 or len(pages) != 25:
            raise ValueError("Tariff inventory must contain exactly 25 pages.")
        if [page.get("page_number") for page in pages] != list(range(1, 26)):
            raise ValueError("Tariff inventory page numbers must be contiguous from 1 to 25.")
        section_codes = {section.get("code") for section in sections}
        if not section_codes or any(page.get("section_code") not in section_codes for page in pages):
            raise ValueError("Every tariff page must reference a known section.")
        required_hashes = ("image_hash", "dense_ocr_hash", "sparse_ocr_hash")
        if any(not all(page.get(field) for field in required_hashes) for page in pages):
            raise ValueError("Every tariff page requires image and OCR hashes.")
