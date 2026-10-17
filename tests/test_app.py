import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import LocalStore, create_server
from structured_parser import parse_quotes


class LocalAppTests(unittest.TestCase):
    def test_batch_source_context_survives_save_without_changing_raw_quote(self):
        source = ('示例乙银行 to 示例甲证券\n900030.SH 27演示债寅 680 103.456\n'
                  '900031.SH 27演示债卯 760 104.567')
        batch = self.request('/api/parse', {'text': source, 'settings': self.settings})
        second = batch['records'][1]
        self.assertEqual(second['action'], '买入')
        self.assertNotIn('示例乙银行', second['raw_text'])
        saved = self.request('/api/save', batch)
        loaded = self.request('/api/batches/' + saved['batch_id'])['records'][1]
        self.assertEqual(loaded['source_context'], second['source_context'])
        self.assertEqual(loaded['batch_context_id'], second['batch_context_id'])
        self.assertEqual(loaded['raw_text'], second['raw_text'])

    def setUp(self):
        self.temp_parent = ROOT / '.local-private' / 'test-temp'
        self.temp_parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_parent)
        self.folder = Path(self.temp.name)
        self.server = create_server(0, self.folder, self.folder / 'config.local.json')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.sample = '900010.SH 27演示债丁 360 净价97.6543 示例甲证券 to 示例乙银行'
        self.settings = {'self_company': '示例甲证券'}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertTrue(self.folder.resolve().is_relative_to(self.temp_parent.resolve()))
        self.temp.cleanup()

    def request(self, route, payload=None, headers=None):
        base = {'Content-Type': 'application/json', 'X-Local-App': 'quote-workbench', 'Origin': self.url}
        base.update(headers or {})
        body = None if payload is None else json.dumps(payload).encode()
        with urlopen(Request(self.url + route, body, base), timeout=5) as response:
            return json.loads(response.read())

    def test_parse_then_explicit_save_and_reload_preserve_original(self):
        parsed = self.request('/api/parse', {'text': self.sample, 'settings': self.settings})
        self.assertFalse((self.folder / 'quotes.sqlite3').exists())
        parsed['records'][0]['quote_price'] = '97.6500'
        parsed['records'][0]['manual_fields'] = ['quote_price']
        saved = self.request('/api/save', parsed)
        self.assertEqual(saved['records'][0]['workflow_status'], '已保存未提交')
        loaded = self.request('/api/batches/' + saved['batch_id'])
        self.assertEqual(loaded['original_input'], self.sample)
        self.assertEqual(loaded['records'][0]['quote_price'], '97.6500')
        self.assertEqual(len(self.request('/api/batches')['batches']), 1)

    def test_saving_new_version_keeps_previous_batch(self):
        parsed = parse_quotes(self.sample, self.settings)
        first = self.request('/api/save', parsed)
        first['records'][0]['workflow_status'] = '已提交'
        second = self.request('/api/save', first)
        self.assertNotEqual(first['batch_id'], second['batch_id'])
        self.assertEqual(second['records'][0]['workflow_status'], '已提交')
        previous = self.request('/api/batches/' + first['batch_id'])
        self.assertEqual(previous['records'][0]['workflow_status'], '已保存未提交')

    def test_external_origin_cannot_post(self):
        with self.assertRaises(HTTPError) as error:
            self.request('/api/parse', {'text': self.sample}, {'Origin': 'https://outside.example'})
        self.assertEqual(error.exception.code, 403)

    def test_business_files_are_not_served(self):
        for route in ('/config.local.json', '/.local-private/quotes.sqlite3', '/examples/quotes.txt'):
            with self.assertRaises(HTTPError) as error:
                self.request(route)
            self.assertEqual(error.exception.code, 404)

    def test_config_is_saved_only_on_request(self):
        self.request('/api/parse', {'text': self.sample, 'settings': self.settings})
        self.assertFalse((self.folder / 'config.local.json').exists())
        self.request('/api/settings', {'settings': self.settings})
        self.assertTrue((self.folder / 'config.local.json').exists())

    def test_invalid_manual_amount_is_visible_in_review(self):
        row = parse_quotes(self.sample, self.settings)['records'][0]
        row['amount_wan'] = '-1'
        reviewed = self.request('/api/review', {'record': row})['record']
        self.assertIn('INVALID_amount_wan', [i['code'] for i in reviewed['issues']])

    def test_business_type_manual_change_persists_and_original_type_stays_traceable(self):
        parsed = self.request('/api/parse', {'text': '组合\n' + self.sample, 'settings': self.settings})
        parsed['original_records'] = copy.deepcopy(parsed['records'])
        record = parsed['records'][0]
        self.assertEqual(record['business_type'], '组合/架桥')
        record.update(business_type='普通报价', manual_fields=['business_type'])
        self.request('/api/review', {'record': record})
        saved = self.request('/api/save', parsed)
        loaded = self.request('/api/batches/' + saved['batch_id'])
        self.assertEqual(loaded['records'][0]['business_type'], '普通报价')
        self.assertEqual(loaded['original_records'][0]['business_type'], '组合/架桥')

    def test_agreement_identifiers_survive_edit_save_and_reload(self):
        parsed = self.request('/api/parse', {'text': self.sample + ' 约定号0007，0018', 'settings': self.settings})
        record = parsed['records'][0]
        self.assertEqual(record['agreement_nos'], ['0007', '0018'])
        record.update(agreement_no='0029、0040', manual_fields=['agreement_no'])
        parsed['records'][0] = self.request('/api/review', {'record': record})['record']
        saved = self.request('/api/save', parsed)
        loaded = self.request('/api/batches/' + saved['batch_id'])['records'][0]
        self.assertEqual(loaded['agreement_no'], '0029、0040')
        self.assertEqual(loaded['agreement_nos'], ['0029', '0040'])
        self.assertEqual(loaded['amount_wan'], '360')

    def test_credit_inventory_metadata_and_missing_quote_survive_save(self):
        sample = '27.3159Y 27演示省债甲 900022.SH 680w 中债隐含：0 发行人：示例甲省（AAA，不在白名单）'
        batch = self.request('/api/parse', {'text': sample, 'settings': self.settings})
        saved = self.request('/api/save', batch)
        loaded = self.request('/api/batches/' + saved['batch_id'])['records'][0]
        self.assertEqual(loaded['bond_name'], '27演示省债甲')
        self.assertEqual(loaded['amount_wan'], '680')
        self.assertIsNone(loaded['quote_price'])
        self.assertIsNone(loaded['yield_candidate'])
        self.assertEqual(loaded['credit_metadata']['china_bond_implied'], '0')
        self.assertEqual(loaded['credit_metadata']['issuer'], '示例甲省')
        self.assertEqual(loaded['raw_text'], sample)

    def test_no_internet_assets_in_app_bootstrap(self):
        data = self.request('/api/bootstrap')
        self.assertEqual(data['settings']['self_company'], '')
        self.assertIn('演示', data['demo'])
        self.assertEqual(data['batches'], [])


if __name__ == '__main__':
    unittest.main()
