from __future__ import annotations

import hashlib
import json
from pathlib import Path


PDF_PATH = Path(".docs/tabela_geral_de_tarifas_pf_pdf.pdf")
OCR_ROOT = Path("tmp/pdfs")
OUTPUT_PATH = Path("knowledge/catalog/tariff_inventory.json")

SECTIONS = (
    ("front_matter", "Capa e navegação", 1, 2),
    ("packages", "Pacotes de serviços", 3, 5),
    ("priority_services", "Serviços prioritários", 6, 8),
    ("cards_checks_transfers", "Cartões, cheques e transferências", 9, 16),
    ("credit_fx_investments", "Crédito, câmbio e investimentos", 17, 22),
    ("legends", "Legendas e observações", 23, 25),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"Missing PDF: {PDF_PATH}")

    pages = []
    for page_number in range(1, 26):
        image = OCR_ROOT / f"ocr-page-{page_number:02}.png"
        dense = OCR_ROOT / f"ocr-page-{page_number:02}.txt"
        sparse = OCR_ROOT / f"ocr-page-{page_number:02}-sparse.txt"
        missing = [path for path in (image, dense, sparse) if not path.exists()]
        if missing:
            raise SystemExit(f"Missing extraction artifacts for page {page_number}: {missing}")
        section_code = next(code for code, _, start, end in SECTIONS if start <= page_number <= end)
        pages.append(
            {
                "page_number": page_number,
                "section_code": section_code,
                "image_hash": sha256(image),
                "dense_ocr_hash": sha256(dense),
                "sparse_ocr_hash": sha256(sparse),
                "review_status": "review_required",
            }
        )

    payload = {
        "catalog_version": 1,
        "source": str(PDF_PATH).replace("\\", "/"),
        "source_hash": sha256(PDF_PATH),
        "effective_from": "2026-07-01",
        "page_count": 25,
        "sections": [
            {
                "code": code,
                "name": name,
                "page_start": start,
                "page_end": end,
                "sort_order": index,
            }
            for index, (code, name, start, end) in enumerate(SECTIONS, start=1)
        ],
        "pages": pages,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(pages)} pages")


if __name__ == "__main__":
    main()
