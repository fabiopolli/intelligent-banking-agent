from __future__ import annotations

import hashlib
import json
from pathlib import Path


CATALOG = Path("knowledge/catalog/tariff_auxiliary.json")


def quoted(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    source = catalog["source"]
    source_id = stable_id("source", source)
    section_id = stable_id("section", f"{source}|packages")
    effective_from = catalog["effective_from"]
    statements = ["BEGIN;"]
    for package in catalog["packages"]:
        dimensions = json.dumps(package.get("dimensions", {}), ensure_ascii=False)
        values = (
            quoted(package["package_id"]), quoted(source_id), quoted(section_id),
            str(package["page_number"]), quoted(package["name"]), quoted("pessoa_fisica"),
            quoted(package["monthly_fee"]), quoted(package["total_services_value"]),
            quoted(dimensions), quoted(effective_from), quoted(package["status"]),
            quoted(package["reviewed_at"]),
        )
        statements.append(
            "INSERT INTO service_packages (package_id,source_id,section_id,page_number,name,audience,"
            "monthly_fee,total_services_value,dimensions,effective_from,status,reviewed_at) VALUES ("
            + ",".join(values)
            + ") ON CONFLICT (package_id) DO UPDATE SET name=EXCLUDED.name,monthly_fee=EXCLUDED.monthly_fee,"
            "total_services_value=EXCLUDED.total_services_value,dimensions=EXCLUDED.dimensions,"
            "status=EXCLUDED.status,reviewed_at=EXCLUDED.reviewed_at;"
        )
    for item in catalog["package_items"]:
        conditions = json.dumps(item.get("conditions", {}), ensure_ascii=False)
        values = (
            quoted(item["package_id"]), quoted(item["item_id"]), quoted(item["service_name"]),
            quoted(item.get("included_quantity")), quoted(item.get("item_value")), quoted(conditions),
        )
        statements.append(
            "INSERT INTO package_items (package_id,item_id,service_name,included_quantity,item_value,conditions) VALUES ("
            + ",".join(values)
            + ") ON CONFLICT (package_id,item_id) DO UPDATE SET service_name=EXCLUDED.service_name,"
            "included_quantity=EXCLUDED.included_quantity,item_value=EXCLUDED.item_value,conditions=EXCLUDED.conditions;"
        )
    for rule in catalog["rules"]:
        values = (
            quoted(rule["rule_id"]), quoted(source_id), str(rule["page_number"]), quoted(rule["rule_code"]),
            quoted(rule["text"]), quoted(effective_from), quoted(rule["status"]), quoted(rule["reviewed_at"]),
        )
        statements.append(
            "INSERT INTO tariff_rules (rule_id,source_id,page_number,rule_code,text,effective_from,status,reviewed_at) VALUES ("
            + ",".join(values)
            + ") ON CONFLICT (rule_id) DO UPDATE SET rule_code=EXCLUDED.rule_code,text=EXCLUDED.text,"
            "status=EXCLUDED.status,reviewed_at=EXCLUDED.reviewed_at;"
        )
    for link in catalog["entry_rule_links"]:
        statements.append(
            "INSERT INTO tariff_entry_rules (tariff_id,rule_id) VALUES ("
            + quoted(link["tariff_id"]) + "," + quoted(link["rule_id"])
            + ") ON CONFLICT (tariff_id,rule_id) DO NOTHING;"
        )
    statements.append("COMMIT;")
    print("\n".join(statements))


if __name__ == "__main__":
    main()
