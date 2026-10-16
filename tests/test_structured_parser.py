import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from structured_parser import parse_quotes, settings_from, short_date, review_record


class StructuredParserTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / 'examples/software_demo.txt').read_text(encoding='utf-8')
        self.settings = {
            'self_company': '示例甲证券', 'self_aliases': ['示例甲'],
            'institution_aliases': {'示例甲': '示例甲证券'},
        }

    def rows(self, **settings):
        return parse_quotes(self.text, {**self.settings, **settings})['records']

    def test_six_records_including_missing_code(self):
        rows = self.rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual([r['amount_wan'] for r in rows], ['360', '240', '480', '600', '90', None])
        self.assertEqual(rows[5]['bond_name'], '27演示债庚')
        self.assertIsNone(rows[5]['bond_code'])
        self.assertIn('CODE_MISSING', [i['code'] for i in rows[5]['issues']])

    def test_theory_and_adjustment_do_not_contaminate_price_or_amount(self):
        row = self.rows()[0]
        self.assertEqual(row['quote_price'], '97.6543')
        self.assertEqual(row['theoretical_price'], '97.7000')
        self.assertEqual(row['adjustment_amount'], '1234')
        self.assertEqual(row['amount_wan'], '360')
        self.assertEqual(row['seller'], '示例甲证券')
        self.assertEqual(row['buyer'], '示例乙银行')

    def test_prefix_dates_w_amount_and_product_names(self):
        a, b = self.rows()[1:3]
        self.assertEqual(a['settlement_date'], '07-14')
        self.assertEqual(a['settlement_speed'], '+0')
        self.assertEqual(a['amount_unit'], '万元')
        self.assertEqual(a['buyer'], '示例丙信托测试产品4号')
        self.assertEqual(b['buyer'], '示例丙信托测试产品5号')
        self.assertEqual(a['request_to'], '示例甲证券')

    def test_buy_template_rate_then_amount_and_named_parties(self):
        row = self.rows()[3]
        self.assertEqual(row['trade_date'], '11-18')
        self.assertEqual(row['term'], '1.25Y')
        self.assertEqual(row['yield_candidate'], '2.18')
        self.assertIsNone(row['quote_price'])
        self.assertEqual(row['amount_wan'], '600')
        self.assertEqual(row['action'], '买入')
        self.assertEqual(row['counterparty'], '示例乙银行')
        self.assertEqual({c['name'] for c in row['contacts']}, {'演示甲', '演示丙'})

    def test_exercise_yield_and_perpetual_term(self):
        row = self.rows()[4]
        self.assertEqual(row['yield_percent'], '2.36')
        self.assertEqual(row['yield_type'], '行权')
        self.assertEqual(row['term'], '3.01Y + N(休1)')
        self.assertEqual(row['action'], '买入')
        self.assertEqual(row['counterparty'], '示例丁')
        self.assertIn('留痕', row['notes_text'])

    def test_k_unit_requires_setting(self):
        self.assertIsNone(self.rows()[5]['amount_wan'])
        row = self.rows(k_multiplier_wan=1000)[5]
        self.assertEqual(row['amount_wan'], '3000')
        self.assertEqual(row['amount_raw'], '3')
        self.assertEqual(row['amount_unit'], 'K')
        self.assertEqual(row['agreement_no'], 'Q88A')
        self.assertEqual(row['settlement_date'], '11-18')
        self.assertEqual(row['contacts'][1]['contact_id'], '880000004')

    def test_company_change_reverses_direction_without_reassigning_report(self):
        rows = self.rows(self_company='示例乙银行', self_aliases=[])
        self.assertEqual(rows[0]['action'], '买入')
        self.assertEqual(rows[3]['action'], '卖出')
        self.assertEqual(rows[4]['action'], '非本方')

    def test_section_and_route_conflict_is_visible(self):
        text = '买入\n900010.SH 27演示债丁 120 净价97.6543 示例甲证券 to 示例乙银行'
        row = parse_quotes(text, self.settings)['records'][0]
        self.assertEqual(row['action'], '待确认')
        self.assertIn('DIRECTION_CONFLICT', [i['code'] for i in row['issues']])

    def test_unknown_to_semantics_remain_unresolved(self):
        row = self.rows(to_direction='unknown')[0]
        self.assertIsNone(row['seller'])
        self.assertEqual(row['action'], '待确认')

    def test_instructions_are_not_record_status_or_approval(self):
        result = parse_quotes(self.text, self.settings)
        self.assertTrue(any('需要提授信' in line['text'] for line in result['context_lines']))
        self.assertTrue(all(r['workflow_status'] == '待核对' for r in result['records']))
        self.assertTrue(all(r['requirements'] == [] for r in result['records']))

    def test_approval_tags_on_name(self):
        row = parse_quotes('900010.SH 27演示债丁【内评】 120 净价97.6543 示例甲 to 示例乙银行', self.settings)['records'][0]
        self.assertEqual(row['bond_name'], '27演示债丁')
        self.assertEqual(row['requirements'], ['内评'])

    def test_amount_that_looks_like_month_day_is_not_a_prefix_date(self):
        row = parse_quotes('900010.SH 27演示债丁 1201 净价97.6543 示例甲 to 示例乙银行', self.settings)['records'][0]
        self.assertEqual(row['amount_wan'], '1201')
        self.assertIsNone(row['trade_date'])

    def test_date_validation_never_invents_year(self):
        self.assertEqual(short_date('1118'), '11-18')
        self.assertEqual(short_date('2027.11.18'), '2027-11-18')
        self.assertIsNone(short_date('1301'))

    def test_compact_full_date_before_code_without_yield(self):
        text = ('20270923 900015.SH 27演示债辛 760 103.456 '
                '示例甲证券 Z90001 to 示例乙银行 Z90002 约定号D55 '
                '（演示甲880000001，演示乙880000004）')
        for configured in (False, True):
            with self.subTest(unlabeled_rate_is_yield=configured):
                row = parse_quotes(text, {**self.settings, 'unlabeled_rate_is_yield': configured})['records'][0]
                self.assertEqual(row['trade_date'], '2027-09-23')
                self.assertEqual(row['amount_wan'], '760')
                self.assertEqual(row['quote_price'], '103.456')
                self.assertIsNone(row['yield_percent'])
                self.assertIsNone(row['yield_candidate'])
                self.assertIsNone(row['price_type'])
                self.assertEqual(row['action'], '卖出')
                self.assertEqual(row['buyer'], '示例乙银行')
                self.assertEqual(row['agreement_no'], 'D55')
                self.assertEqual([c['raw_line'] for c in row['trading_codes']], ['Z90001', 'Z90002'])
                self.assertEqual([c['contact_id'] for c in row['contacts']], ['880000001', '880000004'])
                self.assertTrue(all(c['institution'] is None for c in row['contacts']))
                self.assertEqual(row['raw_text'], text)

    def test_compact_full_date_with_optional_unlabeled_yield(self):
        row = parse_quotes('20270923 900015.SH 27演示债辛 760 2.47 103.456 示例甲证券 to 示例乙银行', self.settings)['records'][0]
        self.assertEqual(row['trade_date'], '2027-09-23')
        self.assertEqual(row['amount_wan'], '760')
        self.assertEqual(row['quote_price'], '103.456')
        self.assertEqual(row['yield_candidate'], '2.47')

    def test_compact_dates_are_validated_without_matching_a_short_suffix(self):
        self.assertEqual(short_date('20280229'), '2028-02-29')
        self.assertIsNone(short_date('20270229'))
        row = parse_quotes('20270229 900015.SH 27演示债辛 760 103.456 示例甲证券 to 示例乙银行', self.settings)['records'][0]
        self.assertIsNone(row['trade_date'])
        self.assertEqual(row['amount_wan'], '760')
        self.assertIsNone(row['yield_candidate'])
        self.assertIn('DATE_INVALID', [issue['code'] for issue in row['issues']])

    def test_compact_date_with_settlement_speed_is_not_a_numeric_quote(self):
        row = parse_quotes('20270923+0 900015.SH 27演示债辛 760 103.456 示例甲证券 to 示例乙银行', self.settings)['records'][0]
        self.assertEqual(row['settlement_date'], '2027-09-23')
        self.assertEqual(row['settlement_speed'], '+0')
        self.assertEqual(row['amount_wan'], '760')
        self.assertEqual(row['quote_price'], '103.456')
        self.assertIsNone(row['yield_candidate'])

    def test_manual_correction_resolves_missing_code_and_preserves_source(self):
        row = self.rows()[5]
        raw = row['raw_text']
        row['bond_code'] = '900014.SH'
        row['manual_fields'] = ['bond_code']
        review_record(row)
        self.assertNotIn('CODE_MISSING', [i['code'] for i in row['issues']])
        self.assertEqual(row['raw_text'], raw)

    def test_invalid_manual_numbers_are_reviewed(self):
        row = self.rows()[0]
        row['amount_wan'] = 'NaN'
        review_record(row)
        self.assertIn('INVALID_amount_wan', [i['code'] for i in row['issues']])

    def test_manual_amount_recomputes_yuan_without_changing_source(self):
        row = self.rows()[0]
        original = row['amount_raw']
        row.update(amount_wan='125.5', manual_fields=['amount_wan'])
        review_record(row)
        self.assertEqual(row['amount_yuan'], '1255000.0')
        self.assertEqual(row['amount_raw'], original)
        row['amount_wan'] = ''
        review_record(row)
        self.assertIsNone(row['amount_yuan'])

    def test_empty_input_and_size_limits(self):
        self.assertEqual(parse_quotes('', self.settings)['record_count'], 0)
        with self.assertRaises(ValueError):
            parse_quotes('x' * 300001, self.settings)
        with self.assertRaises(ValueError):
            settings_from({'self_company': []})


if __name__ == '__main__':
    unittest.main()
