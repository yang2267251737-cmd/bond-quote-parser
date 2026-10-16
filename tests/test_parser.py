import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quote_parser import load_config, parse_text, csv_value

BASE = Path(__file__).resolve().parents[1]


class QuoteParserTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def parse(self, text, **overrides):
        config = copy.deepcopy(self.config)
        config.update(overrides)
        return parse_text(text, config)

    def test_fictional_demo_four_records_and_prices(self):
        result = self.parse((BASE / "examples/demo.txt").read_text(encoding="utf-8"))
        rows = result["records"]
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["quote_price"] for r in rows],
                         ["96.4321", "101.5678", "103.2468", "103.2499"])
        self.assertEqual([r["amount_wan"] for r in rows], ["120", "250", "80", "80"])
        self.assertEqual(rows[0]["price_type"], "净价")
        self.assertTrue(all(r["price_type"] is None for r in rows[1:]))
        self.assertEqual(rows[1]["yield_candidate"], "2.75")
        self.assertIsNone(rows[1]["yield_percent"])

    def test_first_record_missing_endpoint_not_filled_by_contacts(self):
        rows = self.parse((BASE / "examples/demo.txt").read_text(encoding="utf-8"))["records"]
        self.assertIsNone(rows[0]["to_party"])
        self.assertEqual(rows[0]["first_hand_party"], "示例甲证券")
        self.assertEqual(rows[0]["contacts"][0]["institution"], "示例甲证券")
        self.assertEqual(rows[0]["trading_codes"][0]["exchange_dealer_code"], "090909")
        self.assertEqual(rows[0]["trading_codes"][2]["trader_code"], "DEMO0001")
        self.assertEqual(rows[1]["trading_codes"], [])

    def test_alias_and_product_name_preserved(self):
        rows = self.parse((BASE / "examples/demo.txt").read_text(encoding="utf-8"))["records"]
        self.assertEqual(rows[1]["request_to_raw"], "示例甲")
        self.assertEqual(rows[1]["request_to"], "示例甲证券")
        self.assertEqual(rows[2]["to_party"], "示例丙信托测试产品9号")
        self.assertIsNone(rows[1]["contacts"][0]["institution"])

    def test_confirmed_conventions_are_opt_in(self):
        r = self.parse("999999991.IB 26演示MTN甲 1000 2.75 101.5678 示例乙 to 示例甲证券",
                       unlabeled_rate_is_yield=True, to_means_seller_to_buyer=True)["records"][0]
        self.assertEqual(r["yield_percent"], "2.75")
        self.assertEqual(r["seller"], "示例乙银行")
        self.assertEqual(r["buyer"], "示例甲证券")
        self.assertIsNone(r["price_type"])

    def test_label_order_can_change_and_explicit_unit_wins(self):
        r = self.parse("999991.SZ 26演示债甲 净价:96.4321 收益率:2.75% 面额:1亿 甲证券 TO 乙银行")["records"][0]
        self.assertEqual(r["amount_wan"], "10000")
        self.assertEqual(r["amount_yuan"], "100000000")
        self.assertEqual(r["yield_percent"], "2.75")
        self.assertEqual(r["from_party"], "甲证券")

    def test_full_width_input_and_arrows_keep_original(self):
        raw = "９９９９９１．ＳＺ　２６演示债甲　１，０００万　净价９６．４３２１　甲证券 → 乙银行"
        r = self.parse(raw)["records"][0]
        self.assertEqual(r["bond_code"], "999991.SZ")
        self.assertEqual(r["quote_price"], "96.4321")
        self.assertEqual(r["amount_wan"], "1000")
        self.assertEqual(r["raw_text"], raw)

    def test_multiline_header_and_no_blank_separator(self):
        raw = "999991.SZ 26演示债甲\n1000 净价96.4321 甲证券 -> 乙银行\n999999992.IB 26演示MTN乙 1000 103.2499 乙银行 to 丙信托"
        rows = self.parse(raw)["records"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["to_party"], "乙银行")
        self.assertEqual(rows[1]["source_line_start"], 3)

    def test_repeated_bond_keeps_different_quotes(self):
        raw = "999991.SZ 26演示债甲 1000 净价99.9000 甲证券 to 乙银行\n999991.SZ 26演示债甲 1000 净价99.9001 甲证券 to 乙银行"
        rows = self.parse(raw)["records"]
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[1]["duplicate_of"])

    def test_exact_duplicates_flagged_but_not_deleted(self):
        line = "999991.SZ 26演示债甲 1000 净价96.4321 甲证券 to 乙银行"
        rows = self.parse(line + "\n" + line)["records"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["duplicate_of"], "Q001")

    def test_missing_unit_cannot_create_nominal_amount(self):
        r = self.parse("999991.SZ 26演示债甲 1000 净价96.4321 甲证券 to 乙银行", default_amount_unit=None)["records"][0]
        self.assertIsNone(r["amount_yuan"])

    def test_quantity_not_silently_converted_to_cash(self):
        r = self.parse("999991.SZ 26演示债甲 1000张 净价96.4321 甲证券 to 乙银行")["records"][0]
        self.assertEqual(r["amount_unit"], "张")
        self.assertIsNone(r["amount_yuan"])

    def test_multiple_explicit_prices_not_arbitrarily_selected(self):
        r = self.parse("999991.SZ 26演示债甲 1000 净价96.4321 全价101.1234 甲证券 to 乙银行")["records"][0]
        self.assertIsNone(r["quote_price"])
        self.assertIn("存在多个价格，未选择", r["issues"])

    def test_unknown_text_is_retained(self):
        raw = "999991.SZ 26演示债甲 1000 净价96.4321 甲证券 to 乙银行\n甲证券 演示甲880000001\n明天再确认结算日"
        r = self.parse(raw)["records"][0]
        self.assertIn("明天再确认结算日", r["unparsed_lines"])
        self.assertEqual(r["raw_text"], raw)

    def test_no_code_and_preamble_not_silently_dropped(self):
        result = self.parse("这是缺代码的报价 1000 99.9")
        self.assertEqual(result["record_count"], 0)
        self.assertTrue(result["input_warnings"])
        result = self.parse("前置说明\n999991.SZ 26演示债甲 1000 净价96.4321 甲证券 to 乙银行")
        self.assertEqual(result["unassigned_preamble"], "前置说明\n")
        self.assertTrue(result["input_warnings"])

    def test_percent_rate_identified_without_threshold_heuristics(self):
        r = self.parse("999991.SZ 26演示债甲 1000 2.75% 96.4321 甲证券 to 乙银行")["records"][0]
        self.assertEqual(r["yield_percent"], "2.75")
        self.assertEqual(r["quote_price"], "96.4321")

    def test_verified_contact_directory(self):
        r = self.parse("999991.SZ 26演示债甲 1000 净价96.4321 甲证券 to 乙银行\n演示甲880000001",
                       contact_directory={"880000001": "经核实机构"})["records"][0]
        self.assertEqual(r["contacts"][0]["institution"], "经核实机构")

    def test_formula_like_csv_text_escaped(self):
        self.assertEqual(csv_value("=1+1"), "'=1+1")
        self.assertEqual(csv_value(None), "")


if __name__ == "__main__":
    unittest.main()
