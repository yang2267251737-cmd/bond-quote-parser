"""Local, auditable bond quote extraction. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent
CODE = re.compile(r"(?<![A-Za-z0-9])(?:\d{6}|\d{9})\.(?:IB|SZ|SH)(?![A-Za-z0-9])", re.I)
NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
UNIT = r"万元面额|亿元面额|万元|亿元|万面额|亿面额|万|亿|元|张|手"
LABEL = re.compile(
    rf"(?P<label>收益率|净价|全价|价格|金额|面额|数量|YTM)\s*[:：=]?\s*"
    rf"(?P<value>{NUMBER})\s*(?P<unit>{UNIT}|%)?", re.I
)
BARE = re.compile(
    rf"(?<![A-Za-z0-9\u4e00-\u9fff.])(?P<value>{NUMBER})"
    rf"(?P<unit>{UNIT}|%)?(?![A-Za-z0-9\u4e00-\u9fff.])"
)
DIRECTION = re.compile(r"(?<![A-Za-z])to(?![A-Za-z])|->|=>|→", re.I)
CONTACT = re.compile(r"(?P<name>[\u4e00-\u9fff]{2,4})\s*(?P<id>\d{6,12})(?!\d)")
META = re.compile(r"深交所交易商代码|交易主体代码|交易员代码")
REQUEST = re.compile(r"请求\s*发\s*([^\s,，;；]+)")


def load_config(path: Path | None = None) -> dict:
    config = json.loads((path or BASE / "config.json").read_text(encoding="utf-8-sig"))
    if config.get("default_amount_unit") not in (None, "万元", "亿元", "元", "张", "手"):
        raise ValueError("default_amount_unit 不受支持")
    if config.get("default_price_type") not in (None, "净价", "全价"):
        raise ValueError("default_price_type 只能是 null、净价或全价")
    for key in ("unlabeled_rate_is_yield", "to_means_seller_to_buyer"):
        if not isinstance(config.get(key), bool):
            raise ValueError(f"{key} 必须为 true 或 false")
    return config


def normalize_with_offsets(raw: str) -> tuple[str, list[int]]:
    """Keep a mapping back to the untouched source even after NFKC expansion."""
    pieces, offsets = [], []
    for index, char in enumerate(raw):
        normalized = unicodedata.normalize("NFKC", char)
        pieces.append(normalized)
        offsets.extend([index] * len(normalized))
    return "".join(pieces), offsets + [len(raw)]


def number(value: str) -> str:
    return format(Decimal(value.replace(",", "")), "f")


def canonical(value: str | None, config: dict) -> str | None:
    if not value:
        return None
    value = value.strip(" \t\r\n:：,，;；")
    return config["institution_aliases"].get(value, value) or None


def parse_record(raw: str, record_id: str, start_line: int, config: dict) -> dict:
    text = unicodedata.normalize("NFKC", raw)
    code = CODE.match(text)
    assert code
    record = {
        "record_id": record_id, "bond_code": code.group().upper(), "bond_name": None,
        "amount_raw": None, "amount_unit": None, "amount_wan": None, "amount_yuan": None,
        "quote_price": None, "price_type": None, "yield_percent": None,
        "yield_candidate": None, "from_party_raw": None, "to_party_raw": None,
        "from_party": None, "to_party": None, "seller": None, "buyer": None,
        "request_to_raw": None, "request_to": None, "first_hand_party": None,
        "contacts": [], "trading_codes": [], "unassigned_numbers": [], "unparsed_lines": [],
        "issues": [], "evidence": {}, "raw_text": raw,
        "source_line_start": start_line,
        "source_line_end": start_line + raw.rstrip("\r\n").count("\n"),
        "duplicate_of": None,
    }

    def issue(message: str) -> None:
        if message not in record["issues"]:
            record["issues"].append(message)

    def evidence(field: str, snippet: str, method: str) -> None:
        record["evidence"][field] = {"snippet_normalized": snippet, "method": method}

    evidence("bond_code", code.group(), "债券代码形态匹配，未核验证券主数据")
    # Contact/metadata lines are never borrowed to fill a missing direction endpoint.
    quote_lines, body_started, metadata_party = [], False, None
    for line in text[code.end():].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        contacts = list(CONTACT.finditer(line))
        is_header = stripped.endswith(":") and not META.search(stripped)
        if contacts or META.search(line) or is_header:
            body_started = True
        if not body_started:
            quote_lines.append(stripped)
            continue
        if is_header:
            metadata_party = canonical(stripped[:-1], config)
            continue
        if META.search(line):
            item = {"institution": metadata_party, "raw_line": stripped}
            dealer = re.search(r"深交所交易商代码\s*:\s*(\d+)", line)
            entity = re.search(r"交易主体代码\s*:\s*(\d+)", line)
            trader = re.search(r"交易员代码\s*:\s*([^\s()]+)\s*\(([^)]+)\)", line)
            if dealer:
                item["exchange_dealer_code"] = dealer.group(1)
            if entity:
                item["trading_entity_code"] = entity.group(1)
            if trader:
                item.update(trader_name=trader.group(1), trader_code=trader.group(2))
            if len(item) == 2:
                issue("交易代码行未能完整识别")
            record["trading_codes"].append(item)
            continue
        if contacts:
            previous_end = 0
            for contact in contacts:
                prefix = line[previous_end:contact.start()].strip()
                organization = canonical(prefix, config) if prefix else None
                verified = config.get("contact_directory", {}).get(contact.group("id"))
                if verified:
                    organization = verified
                record["contacts"].append({
                    "name": contact.group("name"), "contact_id": contact.group("id"),
                    "institution": organization, "raw_line": stripped,
                    "affiliation_method": "已核验通讯录" if verified else "同行显式前缀" if prefix else "未知",
                })
                if not organization:
                    issue("部分联系人未写所属机构，未按出现顺序绑定")
                previous_end = contact.end()
            trailing = line[previous_end:].strip()
            if trailing:
                record["unparsed_lines"].append(trailing)
                issue("存在未解析的联系人行尾文字")
            continue
        record["unparsed_lines"].append(stripped)
        issue("存在未解析的补充文字")

    quote = " ".join(quote_lines)
    name = re.match(r"([^\s]+)\s*", quote)
    if name and not re.fullmatch(rf"{NUMBER}(?:{UNIT})?", name.group(1)):
        record["bond_name"] = name.group(1)
        evidence("bond_name", name.group(1), "代码后的首个文本词；未核验代码简称对应关系")
        quote = quote[name.end():]
    else:
        issue("缺少债券简称")

    request = REQUEST.search(quote)
    if request:
        record["request_to_raw"] = request.group(1)
        record["request_to"] = canonical(request.group(1), config)
        evidence("request_to", request.group(), "请求发标签；机构别名字典精确匹配")
        request_tail = quote[request.end():].strip()
        if request_tail:
            record["unparsed_lines"].append(request_tail)
            issue("存在未解析的请求行尾文字")
        quote = quote[:request.start()].strip()

    route = DIRECTION.search(quote)
    left = quote[:route.start()] if route else quote
    right = quote[route.end():].strip() if route else ""
    if not route:
        issue("缺少 to/箭头方向标记")

    # Explicitly labelled fields may be reordered. Unlabelled values retain source order.
    masked = list(left)
    amount_values, price_values, yield_values, bare = [], [], [], []
    for match in LABEL.finditer(left):
        label, val, unit = match.group("label"), number(match.group("value")), match.group("unit")
        item = {"value": val, "unit": unit, "snippet": match.group(), "explicit": True}
        if label in ("金额", "面额", "数量"):
            amount_values.append(item)
        elif label in ("净价", "全价", "价格"):
            item["price_type"] = label if label != "价格" else None
            price_values.append(item)
        else:
            yield_values.append(item)
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    remaining = "".join(masked)
    for match in BARE.finditer(remaining):
        bare.append({"value": number(match.group("value")), "unit": match.group("unit"),
                     "snippet": match.group(), "explicit": False})
        masked[match.start():match.end()] = " " * (match.end() - match.start())

    if not amount_values and bare:
        amount_values.append(bare.pop(0))
    if len(amount_values) == 1:
        amount = amount_values[0]
        unit = amount["unit"] or config.get("default_amount_unit")
        unit = {"万": "万元", "万面额": "万元", "万元面额": "万元", "亿": "亿元",
                "亿面额": "亿元", "亿元面额": "亿元"}.get(unit, unit)
        record.update(amount_raw=amount["value"], amount_unit=unit)
        method = "显式金额标签" if amount["explicit"] else "模板约定：首个无标签数字为金额"
        method += "；原文单位" if amount["unit"] else "；配置默认单位" if unit else "；单位缺失"
        evidence("amount_raw", amount["snippet"], method)
        factor = {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}.get(unit)
        if factor is not None:
            yuan = Decimal(amount["value"]) * factor
            record.update(amount_yuan=format(yuan, "f"), amount_wan=format(yuan / 10000, "f"))
        else:
            issue("金额单位缺失或为数量单位，未换算面额")
        if Decimal(amount["value"]) <= 0:
            issue("金额非正数")
        if unit == "%":
            issue("金额位置出现百分号，可能缺失金额或字段错位")
    else:
        issue("缺少金额" if not amount_values else "存在多个金额，未选择")
        record["unassigned_numbers"].extend(amount_values)

    # A percent sign is sufficient to identify a rate; basis (YTM/call/etc.) stays unspecified.
    percent_values = [item for item in bare if item["unit"] == "%"]
    yield_values.extend(percent_values)
    bare = [item for item in bare if item["unit"] != "%"]
    if not price_values and bare:
        item = bare.pop()
        item["price_type"] = config.get("default_price_type")
        price_values.append(item)
    if not yield_values and len(bare) == 1:
        candidate = bare.pop()
        if config.get("unlabeled_rate_is_yield"):
            yield_values.append(candidate)
        else:
            record["yield_candidate"] = candidate["value"]
            record["unassigned_numbers"].append(candidate)
            evidence("yield_candidate", candidate["snippet"], "金额与价格之间的数字，仅作为候选")
            issue("中间数字未注明含义，候选收益率待确认")
    if len(price_values) == 1:
        price = price_values[0]
        price_type = price.get("price_type") or config.get("default_price_type")
        record.update(quote_price=price["value"], price_type=price_type)
        evidence("quote_price", price["snippet"], "显式价格标签" if price["explicit"] else "模板约定：最后一个无标签数字为价格")
        if not price_type:
            issue("价格未注明净价或全价")
        if price["unit"]:
            issue("价格带有额外单位，请核实字段类型")
    else:
        issue("缺少价格" if not price_values else "存在多个价格，未选择")
        record["unassigned_numbers"].extend(price_values)
    if len(yield_values) == 1:
        rate = yield_values[0]
        record["yield_percent"] = rate["value"]
        evidence("yield_percent", rate["snippet"], "收益率标签/百分号" if rate["explicit"] or rate["unit"] == "%" else "用户确认的无标签收益率口径")
    elif len(yield_values) > 1:
        issue("存在多个收益率，未选择")
        record["unassigned_numbers"].extend(yield_values)
    if bare:
        record["unassigned_numbers"].extend(bare)
        issue("存在多余无标签数字")

    left_party = " ".join("".join(masked).split()).strip(" ,，;；")
    first_hand = "(先手)" in left_party or "(先手)" in right
    first_on_left = "(先手)" in left_party
    record["from_party_raw"] = left_party or None
    record["to_party_raw"] = right or None
    record["from_party"] = canonical(left_party.replace("(先手)", ""), config)
    record["to_party"] = canonical(right.replace("(先手)", ""), config)
    if first_hand:
        record["first_hand_party"] = record["from_party"] if first_on_left else record["to_party"]
    for field in ("from_party", "to_party"):
        if not record[field]:
            issue("缺少 to 左侧机构" if field == "from_party" else "缺少 to 右侧机构")
        else:
            evidence(field, record[field + "_raw"], "to 两端原文；别名仅精确替换，保留产品全称")
            if re.search(r"[\d%]|净价|全价|请求", record[field]) and not re.search(r"号$", record[field]):
                issue("方向端点含未解析字段，请核实机构边界")
    if config.get("to_means_seller_to_buyer"):
        record.update(seller=record["from_party"], buyer=record["to_party"])
    else:
        issue("to 的买卖方向口径尚未确认")
    record["extraction_status"] = "待复核" if record["issues"] else "字段完整"
    return record


def parse_text(raw: str, config: dict) -> dict:
    text, offsets = normalize_with_offsets(raw)
    anchors = list(CODE.finditer(text))
    records, warnings, seen = [], [], {}
    if not anchors:
        warnings.append("未找到支持的债券代码；原文已保留，请人工核对，不能视为零笔报价")
    preamble_end = offsets[anchors[0].start()] if anchors else len(raw)
    preamble = raw[:preamble_end]
    if preamble.strip() and anchors:
        warnings.append("首个债券代码之前有未归属文字，请检查前置说明或交易代码")
    for index, anchor in enumerate(anchors):
        start = offsets[anchor.start()]
        end = offsets[anchors[index + 1].start()] if index + 1 < len(anchors) else len(raw)
        source = raw[start:end]
        record = parse_record(source, f"Q{index + 1:03d}", raw[:start].count("\n") + 1, config)
        fingerprint = hashlib.sha256(" ".join(unicodedata.normalize("NFKC", source).split()).encode("utf-8")).hexdigest()
        record["source_hash"] = fingerprint
        if fingerprint in seen:
            record["duplicate_of"] = seen[fingerprint]
            record["issues"].append("与前文完整文本重复，已标记但未删除")
            record["extraction_status"] = "待复核"
        else:
            seen[fingerprint] = record["record_id"]
        records.append(record)
    return {"schema_version": "0.1", "config_snapshot": config, "records": records,
            "input_warnings": warnings, "unassigned_preamble": preamble,
            "original_input": raw, "record_count": len(records),
            "review_count": sum(bool(record["issues"]) for record in records)}


COLUMNS = [
    ("record_id", "记录ID"), ("bond_code", "债券代码"), ("bond_name", "债券简称"),
    ("amount_raw", "金额原值"), ("amount_unit", "金额单位"), ("amount_wan", "面额_万元"),
    ("quote_price", "报价价格"), ("price_type", "价格类型"),
    ("yield_percent", "收益率_pct"), ("yield_candidate", "待确认数字"),
    ("from_party", "to左侧机构"), ("to_party", "to右侧机构"),
    ("seller", "卖方"), ("buyer", "买方"), ("request_to_raw", "请求发原文"),
    ("request_to", "请求发机构"), ("first_hand_party", "先手机构"),
    ("contacts", "联系人"), ("trading_codes", "交易代码补充"),
    ("extraction_status", "识别状态"), ("issues", "复核原因"),
    ("source_line_start", "原文起始行"), ("raw_text", "原文"),
]


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    # Prevent chat text from becoming an Excel formula on opening a CSV.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="报价聊天文本 → 可复核 CSV/JSON（全部本地处理）")
    parser.add_argument("input", type=Path, help="UTF-8 文本路径")
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--out", type=Path, default=BASE / "outputs")
    args = parser.parse_args()
    result = parse_text(args.input.read_text(encoding="utf-8-sig"), load_config(args.config))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "quotes.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.out / "quotes.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([label for _, label in COLUMNS])
        writer.writerows([[csv_value(record[key]) for key, _ in COLUMNS] for record in result["records"]])
    counts = Counter(issue for record in result["records"] for issue in record["issues"])
    print(json.dumps({"records": result["record_count"], "need_review": result["review_count"],
                      "issues": dict(counts), "input_warnings": result["input_warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
