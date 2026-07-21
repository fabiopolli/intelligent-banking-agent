from __future__ import annotations

import json
from pathlib import Path


TARIFF_INVENTORY_PATH = Path("knowledge/catalog/tariff_inventory.json")


class TariffCatalogLoader:
    def __init__(self, inventory_path: Path = TARIFF_INVENTORY_PATH) -> None:
        self._inventory_path = inventory_path

    def load_inventory(self) -> dict:
        payload = json.loads(self._inventory_path.read_text(encoding="utf-8"))
        self._validate_inventory(payload)
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
