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

    def test_no_internet_assets_in_app_bootstrap(self):
        data = self.request('/api/bootstrap')
        self.assertEqual(data['settings']['self_company'], '')
        self.assertIn('演示', data['demo'])
        self.assertEqual(data['batches'], [])


if __name__ == '__main__':
    unittest.main()
