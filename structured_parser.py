"""Context-aware local quote extraction for the paste-and-review application."""
from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from quote_parser import CODE, NUMBER

DEFAULT_SETTINGS = {
    "self_company": "", "self_aliases": [], "institution_aliases": {},
    "default_amount_unit": "万元", "to_direction": "seller_to_buyer",
    "k_multiplier_wan": None, "unlabeled_rate_is_yield": False,
}
SECTION = re.compile(r"^\s*(?:\d+\s*[、.)]\s*)?(买入|卖出|组合|架桥|普通报价)(?:\s*[-—]\s*(.*))?\s*$")
NAME_START = re.compile(r"^\s*(\d{2}[\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff]*)")
ROUTE = re.compile(r"(?<![A-Za-z])to(?![A-Za-z])|->|=>|→|(?<=\s)出(?=\s)", re.I)
CONTACT = re.compile(r"([\u4e00-\u9fff]{2,4})\s*(\d{6,12})(?!\d)")
DATE_TOKEN = r"(?<!\d)(?:\d{8}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[./-]\d{1,2}|\d{4})(?!\d)"
AMOUNT_UNIT = r"万元面额|亿元面额|万元|亿元|万面额|亿面额|万|亿|元|张|手|[wWkK]"
BARE = re.compile(rf"(?<![A-Za-z0-9\u4e00-\u9fff.])({NUMBER})(?:\s*(%))?(?![A-Za-z0-9\u4e00-\u9fff.])")
WORKFLOW_STATES = ("待核对", "已保存未提交", "已提交")
BUSINESS_TYPES = ("普通报价", "回推要素", "组合/架桥")
UNSIGNED_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
AMOUNT_PART = rf"{UNSIGNED_NUMBER}(?:\s*(?:{AMOUNT_UNIT}))?"
ADDITIVE_AMOUNT = rf"{AMOUNT_PART}(?:\s*\+\s*{AMOUNT_PART})+"
AGREEMENT = re.compile(r"约定(?:号|编号)\s*:?\s*([A-Za-z0-9]+(?:\s*[,、/]\s*[A-Za-z0-9]+)*)")
# User-supplied working ranges, used as hints rather than validity or market rules.
COMMON_PRICE_MIN, COMMON_PRICE_MAX = Decimal(80), Decimal(120)
SMALL_FACE_AMOUNT_WAN = Decimal(200)


def amount_unit(value):
    return {"w": "万元", "W": "万元", "万": "万元", "万元面额": "万元", "万面额": "万元",
            "亿": "亿元", "亿元面额": "亿元", "亿面额": "亿元", "k": "K"}.get(value, value)


def amount_factor(unit, settings):
    if unit == "K":
        return Decimal(settings["k_multiplier_wan"]) * 10000 if settings["k_multiplier_wan"] else None
    return {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}.get(unit)


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def dec(value: str) -> str:
    return format(Decimal(value.replace(",", "")), "f")


def clean(value: str) -> str:
    return value.strip(" \t\n,:;，；：")


def settings_from(value: dict | None = None) -> dict:
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if value:
        settings.update({key: value[key] for key in DEFAULT_SETTINGS if key in value})
    if not isinstance(settings["self_company"], str) or len(settings["self_company"]) > 120:
        raise ValueError("本方公司格式不正确")
    if not isinstance(settings["self_aliases"], list) or any(not isinstance(v, str) or len(v) > 120 for v in settings["self_aliases"]):
        raise ValueError("本方别名格式不正确")
    if not isinstance(settings["institution_aliases"], dict) or len(settings["institution_aliases"]) > 500:
        raise ValueError("机构字典格式不正确")
    if any(not isinstance(k, str) or not isinstance(v, str) or max(len(k), len(v)) > 160 for k, v in settings["institution_aliases"].items()):
        raise ValueError("机构字典格式不正确")
    if settings["to_direction"] not in ("seller_to_buyer", "buyer_to_seller", "unknown"):
        raise ValueError("to 方向配置无效")
    if settings["default_amount_unit"] not in ("万元", "亿元", "元", None):
        raise ValueError("默认金额单位无效")
    if settings["k_multiplier_wan"] not in (None, 1000):
        raise ValueError("K 单位配置无效")
    if not isinstance(settings["unlabeled_rate_is_yield"], bool):
        raise ValueError("无标签收益率配置无效")
    settings["self_company"] = clean(settings["self_company"])
    return settings


def institution(value: str | None, settings: dict) -> str | None:
    if not value:
        return None
    value = clean(value)
    value = settings["institution_aliases"].get(value, value)
    own = settings["self_company"]
    if own and value in [own, *settings["self_aliases"]]:
        return own
    return value or None


def short_date(value: str) -> str | None:
    try:
        parts = re.split(r"[-/.]", value)
        if len(parts) == 3:
            return date(*map(int, parts)).isoformat()
        if len(value) == 8 and value.isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
        if len(parts) == 2:
            month, day = map(int, parts)
        elif len(value) == 4:
            month, day = int(value[:2]), int(value[2:])
        else:
            return None
        date(2000, month, day)  # Validate only; never infer the actual trading year.
        return f"{month:02d}-{day:02d}"
    except ValueError:
        return None


def split_records(raw: str) -> tuple[list[dict], list[dict]]:
    records, context_lines, current, pending = [], [], None, []
    context = {"section_action": None, "section_label": None, "section_owner": None,
               "business_type": "普通报价", "section_id": None, "section_title": None}

    def keep_unassigned():
        context_lines.extend({"line": number, "text": value, "unassigned_header": True} for number, value in pending)
        pending.clear()

    for line_number, line in enumerate(raw.splitlines(), 1):
        text = normalized(line).strip()
        if not text:
            continue
        section = SECTION.fullmatch(text)
        owner = re.match(r"^(.+?)固收.*每日要素(?:[-—].*)?$", text)
        instruction = re.match(r"^(?:需要提授信|已保存未提交标|已提交标)", text)
        if section or owner or instruction:
            if current:
                records.append(current)
                current = None
            keep_unassigned()
            context_lines.append({"line": line_number, "text": line})
            if owner:
                context["section_owner"] = clean(owner.group(1))
                context["section_action"] = context["section_label"] = None
                context.update(business_type="普通报价", section_id=None, section_title=None)
            if section:
                label = section.group(1)
                context["section_action"] = label if label in ("买入", "卖出") else None
                context["section_label"] = section.group(2)
                kind = "组合/架桥" if label in ("组合", "架桥") else "回推要素" if "回推" in (section.group(2) or "") else "普通报价"
                context.update(business_type=kind, section_id=f"S{line_number:03d}", section_title=line)
            continue
        if CODE.search(text) or NAME_START.match(text):
            if current:
                records.append(current)
            current = {"lines": [*pending, (line_number, line)], "quote_line_index": len(pending), "context": context.copy()}
            pending.clear()
        elif ROUTE.search(text) or re.fullmatch(rf"{DATE_TOKEN}(?:\s*\+\s*[0-2])?\s*[,;]?", text):
            if current:
                records.append(current)
                current = None
            if ROUTE.search(text) and any(ROUTE.search(normalized(value)) for _, value in pending):
                keep_unassigned()
            pending.append((line_number, line))
        elif pending:
            pending.append((line_number, line))
        elif current:
            current["lines"].append((line_number, line))
        else:
            context_lines.append({"line": line_number, "text": line})
    if current:
        records.append(current)
    keep_unassigned()
    return records, context_lines


def parse_one(segment: dict, index: int, settings: dict) -> dict:
    lines = segment["lines"]
    raw = "\n".join(line for _, line in lines)
    context = segment["context"]
    row = {field: None for field in (
        "bond_code", "bond_name", "amount_raw", "amount_unit", "amount_wan", "amount_yuan",
        "quote_price", "price_type", "yield_percent", "yield_candidate", "yield_type", "term",
        "trade_date", "settlement_date", "settlement_speed", "date_raw", "theoretical_price",
        "adjustment_amount", "from_party", "to_party", "seller", "buyer", "counterparty",
        "request_to", "first_hand_party", "agreement_no", "message_time", "duplicate_of",
    )}
    row.update(record_id=f"Q{index:03d}", action="待确认", section_action=context["section_action"],
               section_owner=context["section_owner"], workflow_kind=context["section_label"],
               business_type=context.get("business_type", "普通报价"), section_id=context.get("section_id"),
               amount_expression=None, amount_components=[], agreement_nos=[], party_name_candidates=[],
               workflow_status="待核对", contacts=[], trading_codes=[], notes=[], requirements=[],
               parser_issues=[], issues=[], evidence={}, manual_fields=[], audit=[], raw_text=raw,
               source_line_start=lines[0][0], source_line_end=lines[-1][0],
               source_hash=hashlib.sha256(" ".join(normalized(raw).split()).encode()).hexdigest())

    def warn(code: str, message: str, field: str = "notes") -> None:
        item = {"code": code, "message": message, "field": field}
        if item not in row["parser_issues"]:
            row["parser_issues"].append(item)

    def evidence(field: str, snippet: str, method: str) -> None:
        row["evidence"][field] = {"snippet": snippet, "method": method}

    def capture_agreement(match):
        row["agreement_nos"].extend(re.split(r"\s*[,、/]\s*", match.group(1)))
        row["agreement_no"] = "、".join(row["agreement_nos"])
        evidence("agreement_no", row["agreement_no"], "完整保留同一标签下及后续行的多个约定号，不自动绑定拆分面额")

    quote_line_index = segment.get("quote_line_index", 0)
    work = normalized(" ".join(line for _, line in lines[:quote_line_index + 1]))
    if context.get("section_title"):
        evidence("business_type", context["section_title"], "来自本笔所属分组标题；业务类型独立于买卖动作")

    def remove(match) -> None:
        nonlocal work
        work = work[:match.start()] + " " * (match.end() - match.start()) + work[match.end():]

    for match in list(re.finditer(r"\((?=[^)]*(?:理论|还我|返还|返费|费用|备注))[^)]*\)", work)):
        row["notes"].append(match.group())
        remove(match)
    inline_metadata = []
    for match in list(re.finditer(r"\(([^)]*)\)", work)):
        if CONTACT.search(match.group(1)):
            inline_metadata.extend(part.strip() for part in re.split(r"[,;]", match.group(1)) if part.strip())
            remove(match)
    for agreement in list(AGREEMENT.finditer(work)):
        capture_agreement(agreement)
        remove(agreement)
    for label in ("内评", "授信"):
        pattern = rf"(?:【{label}】|\[{label}\])"
        for match in list(re.finditer(pattern, work)):
            row["requirements"].append(label)
            remove(match)
    for word in ("留痕", "先手"):
        if word in work:
            row["notes"].append(word)
            work = work.replace(f"({word})", " " * (len(word) + 2)).replace(word, " " * len(word))

    theory = re.search(rf"理论(?:价格|价)?\s*[:：]?\s*({NUMBER})", normalized(raw))
    adjustment = re.search(rf"(?:还我|返还|返费|费用)\s*[:：]?\s*({NUMBER})", normalized(raw))
    if theory:
        row["theoretical_price"] = dec(theory.group(1))
        evidence("theoretical_price", theory.group(), "理论价格标签，独立于实际报价")
        for match in list(re.finditer(rf"理论(?:价格|价)?\s*[:：]?\s*{NUMBER}", work)):
            row["notes"].append(match.group())
            remove(match)
    if adjustment:
        row["adjustment_amount"] = dec(adjustment.group(1))
        warn("ADJUSTMENT", "存在返还/费用约定，金额单位与处理方式需人工核对", "adjustment_amount")

    code = CODE.search(work)
    if code:
        row["bond_code"] = code.group().upper()
        after = re.match(r"\s*([^\s,，]+)", work[code.end():])
        if after:
            row["bond_name"] = after.group(1)
            start, end = code.end() + after.start(), code.end() + after.end()
            work = work[:start] + " " * (end - start) + work[end:]
        evidence("bond_code", code.group(), "代码形态识别，未连接证券主数据")
        remove(code)
    else:
        quote_offset = len(normalized(" ".join(line for _, line in lines[:quote_line_index]))) + 1 if quote_line_index else 0
        name = NAME_START.match(work[quote_offset:])
        if name:
            row["bond_name"] = name.group(1)
            start, end = quote_offset + name.start(), quote_offset + name.end()
            work = work[:start] + " " * (end - start) + work[end:]

    for match in list(re.finditer(rf"({DATE_TOKEN})\s*\+\s*([0-2])", work)):
        parsed = short_date(match.group(1))
        if parsed:
            row.update(settlement_date=parsed, settlement_speed="+" + match.group(2), date_raw=match.group())
            evidence("settlement_date", match.group(), "日期+清算速度写法；缺失年份时只保留月日")
            remove(match)
    for match in list(re.finditer(rf"({DATE_TOKEN})\s*交易", work)):
        parsed = short_date(match.group(1))
        if parsed:
            row["trade_date"] = parsed
            row["date_raw"] = match.group()
            evidence("trade_date", match.group(), "交易日期标签")
            remove(match)
    leading_date = re.match(rf"\s*({DATE_TOKEN})(?=\s)", work) if code and code.start() > 0 else None
    if leading_date:
        parsed = short_date(leading_date.group(1))
        row["date_raw"] = leading_date.group(1)
        if parsed:
            row["trade_date"] = parsed
            evidence("trade_date", leading_date.group(1), "代码前的首部日期；按日历校验后提取，未参与金额或收益率分配")
            warn("DATE_ROLE", "首部无标签日期作为交易日候选，需核对日期用途", "trade_date")
        else:
            row["notes"].append("无效日期: " + leading_date.group(1))
            warn("DATE_INVALID", "首部日期无效，已保留原文且不作为金额或收益率", "trade_date")
        remove(leading_date)
    term = re.search(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?\s*Y(?:\s*\+\s*N)?(?:\s*\([^)]*\))?", work, re.I)
    if term:
        row["term"] = term.group().strip()
        evidence("term", term.group(), "Y 期限及可选 +N / 休息日说明")
        remove(term)
    request = re.search(r"请求\s*(?:发\s*)?([^\s,，;；]+)", work)
    if request:
        row["request_to"] = institution(request.group(1), settings)
        evidence("request_to", request.group(), "请求/请求发标签")
        remove(request)

    prices = list(re.finditer(rf"(净价|全价|价格)\s*[:=]?\s*({NUMBER})", work))
    if len(prices) == 1:
        row.update(quote_price=dec(prices[0].group(2)), price_type=prices[0].group(1) if prices[0].group(1) != "价格" else None)
        evidence("quote_price", prices[0].group(), "显式价格标签")
    elif len(prices) > 1:
        warn("PRICE_CONFLICT", "存在多个实际价格，请手工选择", "quote_price")
    for match in prices:
        remove(match)
    rate_patterns = [rf"(行权收益率|到期收益率|收益率|YTM)\s*[:=]?\s*({NUMBER})\s*%?",
                     rf"({NUMBER})\s*(行权|到期)(?:收益率)?\s*%?"]
    rates = []
    for n, pattern in enumerate(rate_patterns):
        for match in list(re.finditer(pattern, work, re.I)):
            value, kind = (match.group(2), match.group(1)) if n == 0 else (match.group(1), match.group(2))
            rates.append((dec(value), "行权" if "行权" in kind else "到期" if "到期" in kind or kind.upper() == "YTM" else "未注明", match.group()))
            remove(match)
    if len(rates) == 1:
        row.update(yield_percent=rates[0][0], yield_type=rates[0][1])
        evidence("yield_percent", rates[0][2], "显式收益率标签")
    elif len(rates) > 1:
        warn("RATE_CONFLICT", "存在多个收益率，请核对口径", "yield_percent")

    amount_tokens = []
    expression_patterns = [rf"(?:金额|面额|数量)\s*[:=]?\s*({ADDITIVE_AMOUNT})(?![A-Za-z0-9\u4e00-\u9fff./+\-])",
                           rf"(?<![A-Za-z0-9\u4e00-\u9fff./+\-])({ADDITIVE_AMOUNT})(?![A-Za-z0-9\u4e00-\u9fff./+\-])"]
    for pattern in expression_patterns:
        for match in list(re.finditer(pattern, work)):
            expression = match.group(1)
            parts = [re.fullmatch(rf"({UNSIGNED_NUMBER})\s*({AMOUNT_UNIT})?", part.strip()) for part in expression.split("+")]
            explicit = {amount_unit(part.group(2)) for part in parts if part.group(2)}
            inherited = next(iter(explicit)) if len(explicit) == 1 else settings["default_amount_unit"]
            components = []
            for part in parts:
                value = dec(part.group(1))
                unit = amount_unit(part.group(2)) or (inherited if len(explicit) < 2 else None)
                factor = amount_factor(unit, settings)
                yuan = Decimal(value) * factor if factor is not None else None
                components.append({"amount_raw": value, "amount_unit": unit,
                                   "amount_wan": format(yuan / 10000, "f") if yuan is not None else None,
                                   "source": part.group()})
            row["amount_components"].extend(components)
            row["amount_expression"] = "；".join(filter(None, (row["amount_expression"], expression)))
            if all(part["amount_wan"] is not None for part in components):
                total = sum((Decimal(part["amount_wan"]) for part in components), Decimal(0))
                amount_tokens.append((format(total, "f"), "万元", expression))
                row["notes"].append(f"拆分面额: {expression}（合计 {format(total, 'f')} 万元；未拆为逐笔成交）")
            else:
                units = {part["amount_unit"] for part in components}
                unit = next(iter(units)) if len(units) == 1 else "未确认"
                total = sum((Decimal(part["amount_raw"]) for part in components), Decimal(0))
                amount_tokens.append((format(total, "f"), unit, expression))
                row["notes"].append("拆分面额原文: " + expression)
                warn("SPLIT_AMOUNT_UNIT", "拆分面额单位未能统一确认，未生成万元合计", "amount_wan")
            remove(match)
    patterns = [rf"(?:金额|面额|数量)\s*[:=]?\s*({NUMBER})\s*({AMOUNT_UNIT})?",
                rf"(?<![A-Za-z0-9.])({NUMBER})\s*({AMOUNT_UNIT})(?![A-Za-z0-9])"]
    for pattern in patterns:
        for match in list(re.finditer(pattern, work)):
            amount_tokens.append((match.group(1), match.group(2), match.group()))
            remove(match)
    bare = [(dec(m.group(1)), m.group(2) or "", m.group().strip()) for m in BARE.finditer(work)]
    for match in list(BARE.finditer(work)):
        remove(match)
    percent = [item for item in bare if item[1] == "%"]
    bare = [item for item in bare if not item[1]]
    if percent:
        if not rates and len(percent) == 1:
            row["yield_candidate"] = percent[0][0]
            warn("RATE_CONTEXT", "百分数作为收益率候选，需确认不是票息或其他利率", "yield_candidate")
        else:
            warn("EXTRA_PERCENT", "存在额外百分数，需核对含义", "yield_percent")
    def looks_like_rate(value):
        return abs(Decimal(value)) < 20

    def looks_like_price(value, common=False):
        low, high = (COMMON_PRICE_MIN, COMMON_PRICE_MAX) if common else (Decimal(20), Decimal(200))
        return low <= Decimal(value) <= high

    # These ranges only disambiguate unlabeled templates. Explicit labels have no range restriction.
    rate_amount_template = (bool(context["section_action"] or re.search(r"\s出\s", work))
                            and not prices and not rates and len(bare) == 2 and looks_like_rate(bare[0][0]))
    if not amount_tokens and bare:
        amount_index = len(bare) - 1 if rate_amount_template and len(bare) == 2 else 0
        # A unique large face amount can appear before or after the quote. Never use
        # this shortcut for other default units, or as a ban on smaller quotations.
        if settings["default_amount_unit"] == "万元" and len(bare) in (2, 3):
            candidates = [n for n, item in enumerate(bare) if Decimal(item[0]) >= SMALL_FACE_AMOUNT_WAN
                          and all(looks_like_price(other[0]) or looks_like_rate(other[0])
                                  for k, other in enumerate(bare) if k != n)]
            if len(candidates) == 1:
                amount_index = candidates[0]
        amount = bare.pop(amount_index)
        amount_tokens.append((amount[0], None, amount[2]))
    if len(amount_tokens) == 1:
        value, unit, snippet = amount_tokens[0]
        unit = unit or settings["default_amount_unit"]
        unit = amount_unit(unit)
        row.update(amount_raw=dec(value), amount_unit=unit)
        factor = amount_factor(unit, settings)
        if unit == "K":
            if factor is None:
                warn("K_UNIT", "K 的金额换算尚未确认，请设置或手工填写万元面额", "amount_wan")
        if factor is not None:
            yuan = Decimal(row["amount_raw"]) * factor
            row.update(amount_yuan=format(yuan, "f"), amount_wan=format(yuan / 10000, "f"))
        elif unit != "K":
            warn("AMOUNT_UNIT", "金额单位未明确或不是面额单位，未换算", "amount_wan")
        evidence("amount_wan", snippet, "显式单位优先；无标签金额按模板和默认单位解释")
    elif len(amount_tokens) > 1:
        warn("AMOUNT_CONFLICT", "存在多个金额，请人工选择", "amount_wan")
    unresolved_pair = False
    if not prices and not rate_amount_template and bare:
        price = None
        if len(bare) == 1:
            # A lone rate-sized number may be a yield-only quote; do not invent a price.
            if rates or not looks_like_rate(bare[0][0]):
                price = bare.pop()
        elif len(bare) == 2 and not rates:
            possibilities = []
            for common in (True, False):
                possibilities = [(p, y) for p in range(2) for y in range(2)
                                 if p != y and looks_like_price(bare[p][0], common) and looks_like_rate(bare[y][0])]
                if possibilities:
                    break
            if len(possibilities) == 1:
                p, y = possibilities[0]
                price, candidate = bare[p], bare[y]
                bare = [candidate]
            else:
                unresolved_pair = True
                warn("PRICE_RATE_AMBIGUOUS", "两个无标签数字无法可靠区分价格与收益率，已保留原值待核对", "quote_price")
        if price:
            row["quote_price"] = price[0]
            evidence("quote_price", price[2], "优先按80–120常见价格区间、再按宽区间消歧；仅单个价格时保留原值；不依赖价格和利率先后顺序")
    if bare and len(bare) == 1 and not rates and not unresolved_pair:
        candidate = bare.pop()
        target = "yield_percent" if settings["unlabeled_rate_is_yield"] else "yield_candidate"
        row[target] = candidate[0]
        row["yield_type"] = "未注明"
        evidence(target, candidate[2], "分组收益率+金额模板" if rate_amount_template else "面额之外的利率候选；可省略价格或百分号，价格与利率允许换序")
        if target == "yield_candidate":
            warn("UNLABELED_RATE", "无标签利率仅作为候选，可修改配置或手工确认", "yield_candidate")
    if bare:
        row["notes"].append("未分配数字: " + ", ".join(item[0] for item in bare))
        warn("EXTRA_NUMBERS", "存在未分配数字，需核对字段顺序")

    def party(text: str) -> str | None:
        text = clean(text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])(?=Z\d{5,}\b)", " ", text, flags=re.I)
        tokens = text.split()
        if not tokens:
            return None
        token = tokens[0]
        known = {settings["self_company"], *settings["self_aliases"],
                 *settings["institution_aliases"].keys(), *settings["institution_aliases"].values()} - {""}
        boundary = None
        if token not in known:
            for prefix in sorted(known, key=len, reverse=True):
                tail = token[len(prefix):] if token.startswith(prefix) else ""
                if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", tail):
                    boundary = (prefix, tail)
                    break
            if boundary is None:
                found = re.fullmatch(r"(.+?(?:证券|银行|资管|信托|基金|期货|保险|理财))([\u4e00-\u9fff]{2,4})", token)
                if found:
                    boundary = found.groups()
            if boundary and re.search(r"有限|公司|集团|资产|管理|证券|银行|信托|基金|保险|理财|投资|产品|计划|专户|组合|资管|期货", boundary[1]):
                boundary = None
        if boundary:
            org = institution(boundary[0], settings)
            row["party_name_candidates"].append({"source": token, "institution": org, "name": boundary[1]})
            row["contacts"].append({"name": boundary[1], "contact_id": None, "institution": org,
                                    "source": token, "name_is_candidate": True})
            row["notes"].append(f"机构姓名暂拆: {token} → {org} / {boundary[1]}")
            warn("PARTY_NAME_BOUNDARY", "机构与姓名粘连，已暂拆为候选，请核对机构/产品全称和联系人", "counterparty")
            tokens[0] = boundary[0]
        org = institution(tokens[0], settings)
        for token in tokens[1:]:
            if re.fullmatch(r"Z\d{5,}", token, re.I):
                row["trading_codes"].append({"institution": org, "raw_line": token, "kind": "Z代码"})
            elif re.fullmatch(r"[\u4e00-\u9fff]{2,4}", token):
                row["contacts"].append({"name": token, "contact_id": None, "institution": org, "source": "机构后的姓名"})
            else:
                row["notes"].append(token)
                warn("PARTY_TAIL", "机构旁有未识别文字，请核对边界", "counterparty")
        return org

    route = ROUTE.search(work)
    if route:
        row["from_party"] = party(work[:route.start()])
        row["to_party"] = party(work[route.end():])
        direction = "seller_to_buyer" if route.group().strip() == "出" else settings["to_direction"]
        if direction == "seller_to_buyer":
            row.update(seller=row["from_party"], buyer=row["to_party"])
        elif direction == "buyer_to_seller":
            row.update(buyer=row["from_party"], seller=row["to_party"])
        else:
            warn("TO_UNKNOWN", "to 的买卖方向未确认", "action")
        evidence("seller", route.group(), "出表示左卖右买" if route.group().strip() == "出" else "按当前 to 方向配置解释")
        if not row["from_party"] or not row["to_party"]:
            warn("ENDPOINT_MISSING", "交易方向有一端机构缺失", "counterparty")
    elif context["section_action"]:
        counterparty = party(work)
        owner = institution(context["section_owner"] or settings["self_company"], settings)
        if context["section_action"] == "买入":
            row.update(buyer=owner, seller=counterparty)
        else:
            row.update(seller=owner, buyer=counterparty)
        evidence("action", context["section_action"], "明确报告归属优先；无报告抬头时分组按当前本方解释")
    else:
        leftovers = clean(work)
        if leftovers:
            row["notes"].append(leftovers)
        warn("DIRECTION_MISSING", "缺少机构方向或买入卖出分组", "action")
    if "先手" in row["notes"]:
        row["first_hand_party"] = row["from_party"]

    metadata_org = None
    for raw_line in [*inline_metadata, *(line for _, line in lines[quote_line_index + 1:])]:
        line = normalized(raw_line).strip()
        timestamp = re.search(r"(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?!\d)", line)
        if timestamp:
            row["message_time"] = timestamp.group()
            line = line[:timestamp.start()] + line[timestamp.end():]
        for agreement in list(AGREEMENT.finditer(line)):
            capture_agreement(agreement)
            line = line[:agreement.start()] + " " * (agreement.end() - agreement.start()) + line[agreement.end():]
        line = line.strip()
        if not line:
            continue
        if re.search(r"交易商代码|交易主体代码|交易员代码", line):
            row["trading_codes"].append({"institution": metadata_org, "raw_line": line})
            continue
        if line.endswith(":") and not re.search(r"询价|联系人", line):
            metadata_org = institution(line[:-1], settings)
            continue
        tagged = re.match(r"(.+?)询价\s*:\s*([\u4e00-\u9fff]{2,4})\s*$", line)
        if tagged:
            row["contacts"].append({"name": tagged.group(2), "contact_id": None, "institution": institution(tagged.group(1), settings), "source": raw_line})
            continue
        line = re.sub(r"^(?:联系人|询价)\s*:\s*", "", line).strip()
        qt = re.search(r"QT\s*号\s*:?\s*(\d{6,12})", line, re.I)
        if qt:
            prefix = line[:qt.start()].strip().split()
            if len(prefix) == 2:
                row["contacts"].append({"name": prefix[1], "contact_id": qt.group(1), "institution": institution(prefix[0], settings), "source": raw_line})
                continue
        contacts = list(CONTACT.finditer(line))
        if contacts:
            previous = 0
            for match in contacts:
                prefix = clean(line[previous:match.start()])
                row["contacts"].append({"name": match.group(1), "contact_id": match.group(2), "institution": institution(prefix, settings), "source": raw_line})
                if not prefix:
                    warn("CONTACT_ORG", "部分联系人未注明机构，未按顺序绑定", "contacts")
                previous = match.end()
            tail = clean(line[previous:])
            if tail:
                row["notes"].append("联系人补充: " + tail)
                warn("CONTACT_TAIL", "联系人补充写法未完全识别，请查看原文", "contacts")
        elif line:
            row["notes"].append(raw_line)
            warn("NOTE_REVIEW", "存在补充文字，请查看原文")

    if len(row["agreement_nos"]) > 1:
        warn("MULTIPLE_AGREEMENTS", "多个约定号已完整保留；与拆分面额的逐笔对应关系未自动绑定", "agreement_no")
    owner = institution(context["section_owner"] or settings["self_company"], settings)
    if route and context["section_action"] and owner:
        routed_action = "买入" if row["buyer"] == owner else "卖出" if row["seller"] == owner else None
        if routed_action != context["section_action"]:
            warn("DIRECTION_CONFLICT", "分组动作与机构方向冲突，请核对", "action")
    own = institution(settings["self_company"], settings)
    if own:
        if row["buyer"] == own and row["seller"] == own:
            warn("SAME_PARTY", "买卖双方均匹配本方公司，请核对别名", "action")
        elif row["buyer"] == own:
            row.update(action="买入", counterparty=row["seller"])
        elif row["seller"] == own:
            row.update(action="卖出", counterparty=row["buyer"])
        elif row["seller"] and row["buyer"]:
            row["action"] = "非本方"
    if any(item["code"] == "DIRECTION_CONFLICT" for item in row["parser_issues"]):
        row["action"] = "待确认"
    row["notes_text"] = "；".join(row["notes"])
    row["requirements_text"] = "、".join(row["requirements"])
    row["contacts_text"] = "；".join(" / ".join(str(c.get(k) or "机构待确认") for k in ("institution", "name")) + (f" / {c['contact_id']}" if c.get('contact_id') else "") for c in row["contacts"])
    return review_record(row)


def review_record(row: dict) -> dict:
    if "agreement_no" in row.get("manual_fields", []) or "agreement_nos" not in row:
        row["agreement_nos"] = [part for part in re.split(r"[,，、/;；\s]+", row.get("agreement_no") or "") if part]
    if not row.get("business_type"):
        row["business_type"] = "回推要素" if "回推" in (row.get("workflow_kind") or "") else "普通报价"
    issues = [item.copy() for item in row.get("parser_issues", []) if item["field"] not in row.get("manual_fields", [])]
    def add(code: str, message: str, field: str):
        if not any(item["code"] == code for item in issues):
            issues.append({"code": code, "message": message, "field": field})
    if not row.get("bond_code"):
        add("CODE_MISSING", "原文未提供债券代码，请手工补充", "bond_code")
    elif not CODE.fullmatch(row["bond_code"]):
        add("CODE_INVALID", "债券代码格式不受支持", "bond_code")
    if not row.get("bond_name"):
        add("NAME_MISSING", "缺少债券简称", "bond_name")
    if row.get("business_type") not in BUSINESS_TYPES:
        add("BUSINESS_TYPE_INVALID", "业务类型无效，请选择普通报价、回推要素或组合/架桥", "business_type")
    for key in ("amount_wan", "quote_price", "yield_percent", "yield_candidate", "theoretical_price", "adjustment_amount"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                parsed = Decimal(str(value))
                if not parsed.is_finite() or (key == "amount_wan" and parsed <= 0):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                add("INVALID_" + key, "数值无效: " + key, key)
    # Recompute hints from current values, including when opening saved batches or editing.
    for key, code, message in (
        ("quote_price", "PRICE_UNUSUAL", "价格超出本机业务常见区间80–120元，已保留原值，请核对"),
        ("amount_wan", "SMALL_FACE_AMOUNT", "面额低于200万元，少于常见业务规模，已保留原值；面额不等于实际成交金额"),
    ):
        try:
            value = Decimal(str(row.get(key)))
            unusual = (value < COMMON_PRICE_MIN or value > COMMON_PRICE_MAX) if key == "quote_price" else 0 < value < SMALL_FACE_AMOUNT_WAN
            if value.is_finite() and unusual:
                add(code, message, key)
        except (InvalidOperation, ValueError):
            pass
    if not row.get("amount_wan"):
        add("AMOUNT_MISSING", "缺少可确认的万元面额", "amount_wan")
    # Current normalized amount must follow manual edits; source amount stays intact.
    if "amount_wan" in row.get("manual_fields", []):
        try:
            amount = Decimal(str(row.get("amount_wan")))
            row["amount_yuan"] = format(amount * 10000, "f") if amount.is_finite() and amount > 0 else None
        except (InvalidOperation, ValueError):
            row["amount_yuan"] = None
    if not any(row.get(key) for key in ("quote_price", "yield_percent", "yield_candidate")):
        add("QUOTE_MISSING", "缺少价格或收益率", "quote_price")
    if row.get("quote_price") and not row.get("price_type"):
        add("PRICE_TYPE", "价格未注明净价或全价", "price_type")
    if row.get("action") == "待确认":
        add("ACTION_UNKNOWN", "本方动作待确认，请核对公司与交易方向", "action")
    if row.get("workflow_status") not in WORKFLOW_STATES:
        row["workflow_status"] = "待核对"
    row["issues"] = issues
    row["extraction_status"] = "待复核" if issues else "字段已提取"
    return row


def parse_quotes(raw: str, options: dict | None = None) -> dict:
    if not isinstance(raw, str):
        raise ValueError("报价内容必须为文本")
    if len(raw) > 300000:
        raise ValueError("文本过长，请分批粘贴（每批最多 30 万字符）")
    settings = settings_from(options)
    segments, context_lines = split_records(raw)
    rows = [parse_one(segment, n + 1, settings) for n, segment in enumerate(segments)]
    seen = {}
    for row in rows:
        if row["source_hash"] in seen:
            row["duplicate_of"] = seen[row["source_hash"]]
            row["parser_issues"].append({"code": "DUPLICATE", "field": "notes", "message": "完整报价重复，已标记但未删除"})
            review_record(row)
        else:
            seen[row["source_hash"]] = row["record_id"]
    warnings = []
    if raw.strip() and not rows:
        warnings.append("没有找到可识别报价；请检查代码或简称，不代表输入中没有报价。")
    if not settings["self_company"]:
        warnings.append("请填写本方公司，以判断相对本方的买卖动作。")
    if any(line.get("unassigned_header") for line in context_lines):
        warnings.append("有日期或机构方向表头未找到对应债券，已保留在未归属文字中，请检查。")
    return {"schema_version": "0.2", "records": rows, "original_input": raw,
            "settings": settings, "context_lines": context_lines, "input_warnings": warnings,
            "record_count": len(rows), "review_count": sum(bool(row["issues"]) for row in rows)}
