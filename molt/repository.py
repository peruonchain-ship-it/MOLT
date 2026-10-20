import json
from datetime import UTC, datetime, timedelta

from .matching import classify, normalize, parse_date


def read_item(row):
    item = json.loads(row["data"])
    item.update({k: row[k] for k in ("first_seen", "last_seen", "changed_at", "stage", "notes", "version")})
    item["classification"], item["status_reason"] = classify(item)
    return item


def list_items(db, q="", city="", family="", classification="", stage="", sort="recent", include_unknown=False,
               followup=False):
    selected = db.settings()["cities"]
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM opportunities ORDER BY changed_at DESC").fetchall()
    result = []
    query = normalize(q)
    for row in rows:
        item = read_item(row)
        if city == "unknown":
            if item["city"] is not None:
                continue
        elif city:
            if item["city"] != city:
                continue
        elif item["city"] not in selected and not (include_unknown and not item["city"]):
            continue
        if family and family not in item["families"]:
            continue
        if classification and item["classification"] != classification:
            continue
        if stage and item["stage"] != stage:
            continue
        if followup and item["stage"] not in ("Revisar", "Cotizar", "Presentada"):
            continue
        if query and query not in normalize(" ".join(str(item.get(k, "")) for k in
                                                    ("title", "buyer", "reference", "notes", "scope"))
                                            + " " + " ".join(e["term"] for e in item["evidence"])):
            continue
        result.append(item)
    if sort == "recent":
        result.sort(key=lambda x: parse_date(x["published"]) or parse_date(x["source_updated"])
                    or datetime.min.replace(tzinfo=UTC), reverse=True)
    elif sort == "score":
        result.sort(key=lambda x: x["score"], reverse=True)
    elif sort == "deadline":
        result.sort(key=lambda x: parse_date(x["deadline"]) or datetime.max.replace(tzinfo=UTC))
    elif sort == "amount":
        # Do not sum or rank mixed currencies as if they were all soles.
        result.sort(key=lambda x: (x["currency"] != "PEN", -(x["amount"] or 0)))
    return result


def dashboard(db):
    items = list_items(db)
    now = datetime.now(UTC)
    stats = {"total": len(items), "open": 0, "review": 0, "historical": 0, "saved": 0, "due": 0,
             "integral": 0, "by_city": {}, "by_family": {}}
    for item in items:
        stats[item["classification"]] += 1
        if item["stage"] in ("Revisar", "Cotizar", "Presentada"):
            stats["saved"] += 1
        deadline = parse_date(item["deadline"])
        if item["classification"] == "open" and deadline and now < deadline < now + timedelta(days=3):
            stats["due"] += 1
        if item["scope"].startswith("Integral"):
            stats["integral"] += 1
        city = item["city"] or "Sin ubicación"
        stats["by_city"][city] = stats["by_city"].get(city, 0) + 1
        for family in item["families"]:
            stats["by_family"][family] = stats["by_family"].get(family, 0) + 1
    with db.connect() as conn:
        stats["unlocated"] = conn.execute("SELECT COUNT(*) FROM opportunities WHERE json_extract(data,'$.city') IS NULL").fetchone()[0]
    return stats
