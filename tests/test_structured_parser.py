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

    def test_price_and_yield_can_appear_in_either_order(self):
        for middle in ('104.2671 2.63', '2.63 104.2671'):
            for amount in ('680', '680w'):
                with self.subTest(middle=middle, amount=amount):
                    row = parse_quotes(f'900000016.IB 27演示PPN甲 {amount} {middle} 示例丁资管 to 示例甲证券', self.settings)['records'][0]
                    self.assertEqual(row['amount_wan'], '680')
                    self.assertEqual(row['quote_price'], '104.2671')
                    self.assertEqual(row['yield_candidate'], '2.63')
                    self.assertIsNone(row['yield_percent'])

    def test_multiline_header_belongs_to_following_bond(self):
        text = ('7.14+0，示例丁资管Z90009 演示丙 to示例甲证券\n'
                '900000016.IB 27演示PPN甲 680 104.2671 2.63')
        row = parse_quotes(text, self.settings)['records'][0]
        self.assertEqual(row['settlement_date'], '07-14')
        self.assertEqual(row['settlement_speed'], '+0')
        self.assertEqual(row['seller'], '示例丁资管')
        self.assertEqual(row['buyer'], '示例甲证券')
        self.assertEqual(row['action'], '买入')
        self.assertEqual(row['contacts'][0]['name'], '演示丙')
        self.assertEqual(row['trading_codes'][0]['raw_line'], 'Z90009')
        self.assertEqual((row['source_line_start'], row['source_line_end']), (1, 2))
        self.assertEqual(row['raw_text'], text)
        self.assertEqual(row['quote_price'], '104.2671')
        self.assertEqual(row['yield_candidate'], '2.63')

    def test_bridge_section_keeps_both_legs_and_separate_headers(self):
        text = ('10、组合\n'
                '7.14+0，示例丁期货 to 示例甲证券，请求示例甲证券\n'
                '900000017.IB 27演示MTN丙(示例) 640 5.73 净价96.4123\n\n'
                '7.14+0，示例甲证券 to 示例乙银行测试产品9号，请求示例甲证券\n'
                '900000017.IB 27演示MTN丙(示例) 640w 净价96.4187')
        rows = parse_quotes(text, self.settings)['records']
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['business_type'] for r in rows], ['组合/架桥', '组合/架桥'])
        self.assertEqual([r['action'] for r in rows], ['买入', '卖出'])
        self.assertEqual([r['counterparty'] for r in rows], ['示例丁期货', '示例乙银行测试产品9号'])
        self.assertEqual([r['amount_wan'] for r in rows], ['640', '640'])
        self.assertEqual([r['quote_price'] for r in rows], ['96.4123', '96.4187'])
        self.assertEqual([r['yield_candidate'] for r in rows], ['5.73', None])
        self.assertTrue(all(r['bond_name'] == '27演示MTN丙(示例)' for r in rows))
        self.assertTrue(all(r['request_to'] == '示例甲证券' for r in rows))
        self.assertTrue(all(r['settlement_date'] == '07-14' for r in rows))
        self.assertEqual([r['source_line_start'] for r in rows], [2, 5])
        self.assertNotIn('测试产品9号', rows[0]['raw_text'])
        self.assertEqual(rows[0]['section_id'], rows[1]['section_id'])
        self.assertEqual(rows[0]['evidence']['business_type']['snippet'], '10、组合')

    def test_business_type_resets_at_next_section(self):
        text = ('组合\n900010.SH 27演示债丁 120 净价97.6543 示例甲证券 to 示例乙银行\n'
                '11、买入-回推要素\n900012.SZ 27演示债戊 120 净价97.6543 示例乙银行 to 示例甲证券\n'
                '12、卖出\n900013.SH 27演示债己 120 净价97.6543 示例甲证券 to 示例乙银行')
        rows = parse_quotes(text, self.settings)['records']
        self.assertEqual([r['business_type'] for r in rows], ['组合/架桥', '回推要素', '普通报价'])

    def test_unassigned_header_is_retained_and_warned(self):
        text = '7.14+0，示例甲证券 to 示例乙银行'
        result = parse_quotes(text, self.settings)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['context_lines'][0]['text'], text)
        self.assertTrue(any('未找到对应债券' in warning for warning in result['input_warnings']))

    def test_ambiguous_pair_is_not_silently_assigned(self):
        row = parse_quotes('900010.SH 27演示债丁 120 97.1 98.2 示例甲证券 to 示例乙银行', self.settings)['records'][0]
        self.assertIsNone(row['quote_price'])
        self.assertIsNone(row['yield_candidate'])
        self.assertIn('PRICE_RATE_AMBIGUOUS', [i['code'] for i in row['issues']])
        self.assertIn('97.1', row['notes_text'])
        self.assertIn('98.2', row['notes_text'])

    def test_buy_section_without_yield_keeps_amount_and_price(self):
        row = parse_quotes('买入\n900010.SH 27演示债丁 760 103.456 示例乙银行 to 示例甲证券', self.settings)['records'][0]
        self.assertEqual(row['amount_wan'], '760')
        self.assertEqual(row['quote_price'], '103.456')
        self.assertIsNone(row['yield_candidate'])

    def test_legacy_rows_get_business_type_without_losing_original(self):
        row = self.rows()[4]
        row.pop('business_type')
        original = row['raw_text']
        review_record(row)
        self.assertEqual(row['business_type'], '回推要素')
        self.assertEqual(row['raw_text'], original)

    def test_header_on_separate_lines_and_missing_code_keep_bond_name(self):
        text = '7.14+0\n示例乙银行 to 示例甲证券\n27演示债庚 760 净价103.456'
        row = parse_quotes(text, self.settings)['records'][0]
        self.assertEqual(row['bond_name'], '27演示债庚')
        self.assertIsNone(row['bond_code'])
        self.assertEqual(row['action'], '买入')
        self.assertEqual(row['amount_wan'], '760')
        self.assertEqual(row['settlement_date'], '07-14')
        self.assertIn('CODE_MISSING', [i['code'] for i in row['issues']])

    def test_numeric_heuristics_do_not_restrict_explicit_labels(self):
        row = parse_quotes('900010.SH 27演示债丁 760 净价15 收益率55% 示例乙银行 to 示例甲证券', self.settings)['records'][0]
        self.assertEqual(row['quote_price'], '15')
        self.assertEqual(row['yield_percent'], '55')

    def test_negative_yield_can_follow_unlabeled_price(self):
        row = parse_quotes('900010.SH 27演示债丁 760 103.456 -0.38 示例乙银行 to 示例甲证券', self.settings)['records'][0]
        self.assertEqual(row['quote_price'], '103.456')
        self.assertEqual(row['yield_candidate'], '-0.38')

    def test_additive_amount_with_optional_yield_and_glued_institution_name(self):
        text = ('2027/9/23\t900018.SH\t27演示债壬\t680+420\t103.246\t\t示例丁资管演示丙 to\t示例甲证券 演示甲\n'
                '2027/9/23\t900019.SH\t27演示债癸\t680+420\t103.267\t2.73\t示例丁资管演示丙 to\t示例甲证券 演示甲 约定号0012，0034')
        rows = parse_quotes(text, self.settings)['records']
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['amount_wan'] for r in rows], ['1100', '1100'])
        self.assertEqual([r['quote_price'] for r in rows], ['103.246', '103.267'])
        self.assertEqual([r['yield_candidate'] for r in rows], [None, '2.73'])
        for row in rows:
            self.assertEqual(row['trade_date'], '2027-09-23')
            self.assertEqual(row['action'], '买入')
            self.assertEqual(row['counterparty'], '示例丁资管')
            self.assertEqual(row['amount_expression'], '680+420')
            self.assertEqual([part['amount_raw'] for part in row['amount_components']], ['680', '420'])
            self.assertEqual(row['party_name_candidates'][0]['source'], '示例丁资管演示丙')
            self.assertIn('PARTY_NAME_BOUNDARY', [item['code'] for item in row['issues']])
        self.assertEqual(rows[1]['agreement_nos'], ['0012', '0034'])
        self.assertEqual(rows[1]['agreement_no'], '0012、0034')
        self.assertIn('MULTIPLE_AGREEMENTS', [item['code'] for item in rows[1]['issues']])
        self.assertTrue(all('agreement_no' not in part for part in rows[1]['amount_components']))
        self.assertEqual(rows[1]['raw_text'], text.splitlines()[1])

    def test_additive_amount_with_explicit_label_and_trailing_unit(self):
        row = parse_quotes('900010.SH 27演示债丁 面额80 + 20w 净价103.456 示例乙银行 to 示例甲证券', self.settings)['records'][0]
        self.assertEqual(row['amount_wan'], '100')
        self.assertEqual(row['amount_yuan'], '1000000')
        self.assertEqual([part['amount_unit'] for part in row['amount_components']], ['万元', '万元'])
        self.assertIsNone(row['yield_candidate'])

    def test_additive_amount_converts_explicit_mixed_units(self):
        row = parse_quotes('900010.SH 27演示债丁 1亿元+500万元 净价103.456 示例乙银行 to 示例甲证券', self.settings)['records'][0]
        self.assertEqual(row['amount_wan'], '10500')
        self.assertEqual([part['amount_wan'] for part in row['amount_components']], ['10000', '500'])

    def test_additive_amount_without_confirmed_unit_is_not_converted(self):
        row = parse_quotes('900010.SH 27演示债丁 80+20 净价103.456 示例乙银行 to 示例甲证券', {**self.settings, 'default_amount_unit': None})['records'][0]
        self.assertIsNone(row['amount_wan'])
        self.assertEqual(row['amount_expression'], '80+20')
        self.assertEqual(row['quote_price'], '103.456')
        self.assertIn('SPLIT_AMOUNT_UNIT', [item['code'] for item in row['issues']])

    def test_additive_k_amount_remains_opt_in(self):
        text = '900010.SH 27演示债丁 1K+2K 净价103.456 示例乙银行 to 示例甲证券'
        self.assertIsNone(parse_quotes(text, self.settings)['records'][0]['amount_wan'])
        row = parse_quotes(text, {**self.settings, 'k_multiplier_wan': 1000})['records'][0]
        self.assertEqual(row['amount_wan'], '3000')

    def test_multiple_agreements_on_following_lines_are_all_preserved(self):
        text = ('900010.SH 27演示债丁 120 净价103.456 示例乙银行 to 示例甲证券\n'
                '约定号E01、E02\n约定编号E03')
        row = parse_quotes(text, self.settings)['records'][0]
        self.assertEqual(row['agreement_nos'], ['E01', 'E02', 'E03'])
        self.assertEqual(row['agreement_no'], 'E01、E02、E03')
        self.assertEqual(row['amount_wan'], '120')

    def test_agreement_manual_edit_updates_identifier_list(self):
        row = self.rows()[5]
        row.update(agreement_no='0008，0019', manual_fields=['agreement_no'])
        review_record(row)
        self.assertEqual(row['agreement_nos'], ['0008', '0019'])

    def test_company_suffix_and_numbered_product_are_not_split_as_contacts(self):
        for name in ('示例丁资管有限公司', '示例乙银行测试产品9号'):
            with self.subTest(name=name):
                row = parse_quotes(f'900010.SH 27演示债丁 120 净价103.456 {name} to 示例甲证券', self.settings)['records'][0]
                self.assertEqual(row['counterparty'], name)
                self.assertEqual(row['party_name_candidates'], [])

    def test_glued_self_alias_is_only_a_contact_candidate(self):
        row = parse_quotes('900010.SH 27演示债丁 120 净价103.456 示例乙银行 to 示例甲演示丙', self.settings)['records'][0]
        self.assertEqual(row['action'], '买入')
        self.assertEqual(row['buyer'], '示例甲证券')
        self.assertTrue(row['contacts'][0]['name_is_candidate'])

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
