"""Loopback-only Python application. No third-party dependencies or cloud calls."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import threading
import uuid
import webbrowser
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from structured_parser import parse_quotes, review_record, settings_from

ROOT = Path(__file__).resolve().parent
EDITABLE_FIELDS = {
    'action', 'bond_code', 'bond_name', 'amount_wan', 'quote_price', 'price_type',
    'yield_percent', 'yield_candidate', 'yield_type', 'term', 'trade_date',
    'settlement_date', 'settlement_speed', 'seller', 'buyer', 'counterparty',
    'request_to', 'contacts_text', 'agreement_no', 'requirements_text',
    'notes_text', 'workflow_status', 'theoretical_price', 'adjustment_amount',
}


class LocalStore:
    def __init__(self, directory: Path, config_path: Path | None = None):
        self.directory = directory
        self.database = directory / 'quotes.sqlite3'
        self.config_path = config_path or ROOT / 'config.local.json'
        self.lock = threading.Lock()

    def settings(self):
        base = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        values = {'institution_aliases': base.get('institution_aliases', {})}
        if self.config_path.is_file():
            values.update(json.loads(self.config_path.read_text(encoding='utf-8-sig')))
        return settings_from(values)

    def save_settings(self, settings):
        settings = settings_from(settings)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix('.tmp')
        with self.lock:
            temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.config_path)
        return settings

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        connection.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, company TEXT NOT NULL, count INTEGER NOT NULL, parent_id TEXT, payload TEXT NOT NULL)')
        return connection

    def list_batches(self):
        if not self.database.is_file():
            return []
        with self.lock, closing(self.connect()) as connection, connection:
            rows = connection.execute('SELECT id,created_at,company,count FROM batches ORDER BY created_at DESC LIMIT 40').fetchall()
        return [dict(zip(('id', 'created_at', 'company', 'count'), row)) for row in rows]

    def read_batch(self, batch_id):
        if not self.database.is_file():
            return None
        with self.lock, closing(self.connect()) as connection, connection:
            row = connection.execute('SELECT payload FROM batches WHERE id=?', (batch_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_batch(self, payload):
        records = payload.get('records')
        if not isinstance(records, list) or not 0 < len(records) <= 500:
            raise ValueError('没有可保存的报价，或单批超过 500 笔')
        settings = settings_from(payload.get('settings'))
        original = payload.get('original_input', '')
        if not isinstance(original, str) or len(original) > 300000:
            raise ValueError('原文格式不正确或过长')
        records = copy.deepcopy(records)
        for record in records:
            if not isinstance(record, dict):
                raise ValueError('记录格式不正确')
            for field in EDITABLE_FIELDS:
                value = record.get(field)
                if value is not None and (not isinstance(value, str) or len(value) > 10000):
                    raise ValueError('字段内容无效: ' + field)
            if record.get('workflow_status') != '已提交':
                record['workflow_status'] = '已保存未提交'
            review_record(record)
        batch_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        saved = {**payload, 'records': records, 'settings': settings,
                 'batch_id': batch_id, 'created_at': created_at}
        encoded = json.dumps(saved, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 4 * 1024 * 1024:
            raise ValueError('单批数据过大，请拆分保存')
        with self.lock, closing(self.connect()) as connection, connection:
            connection.execute('INSERT INTO batches VALUES (?,?,?,?,?,?)',
                               (batch_id, created_at, settings['self_company'], len(records), payload.get('batch_id'), encoded))
        return saved


def make_handler(store: LocalStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'QuoteWorkbench'

        def log_message(self, *_):
            pass  # Business input must not enter access logs.

        def allowed_host(self):
            return self.headers.get('Host', '') in (
                f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def send(self, status, content, content_type='application/json; charset=utf-8'):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if not self.allowed_host():
                return self.send(403, {'error': '仅接受本机地址访问'})
            path = urlsplit(self.path).path
            try:
                if path == '/api/bootstrap':
                    return self.send(200, {'settings': store.settings(), 'batches': store.list_batches(),
                                           'demo': (ROOT / 'examples/software_demo.txt').read_text(encoding='utf-8')})
                if path == '/api/batches':
                    return self.send(200, {'batches': store.list_batches()})
                match = re.fullmatch(r'/api/batches/([a-f0-9]{32})', path)
                if match:
                    payload = store.read_batch(match.group(1))
                    return self.send(200, payload) if payload else self.send(404, {'error': '本地批次不存在'})
                files = {'/': ('index.html', 'text/html; charset=utf-8'),
                         '/app.css': ('app.css', 'text/css; charset=utf-8'),
                         '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
                if path in files:
                    filename, content_type = files[path]
                    return self.send(200, (ROOT / 'web' / filename).read_bytes(), content_type)
                return self.send(404, {'error': '页面不存在'})
            except (OSError, ValueError, sqlite3.Error):
                return self.send(500, {'error': '本地文件或设置读取失败，请检查权限和配置'})

        def do_POST(self):
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.allowed_host() or self.headers.get('X-Local-App') != 'quote-workbench' or self.headers.get('Origin') not in (None, *allowed_origins):
                return self.send(403, {'error': '请求来源不正确，请从本地软件页面操作'})
            if self.headers.get_content_type() != 'application/json':
                return self.send(415, {'error': '请求必须为 JSON'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0 or size > 4 * 1024 * 1024:
                    return self.send(413, {'error': '请求过大或为空，请分批处理'})
                payload = json.loads(self.rfile.read(size).decode('utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                if not isinstance(payload, dict):
                    raise ValueError('请求格式不正确')
                path = urlsplit(self.path).path
                if path == '/api/parse':
                    return self.send(200, parse_quotes(payload.get('text', ''), payload.get('settings')))
                if path == '/api/settings':
                    return self.send(200, {'settings': store.save_settings(payload.get('settings'))})
                if path == '/api/save':
                    return self.send(200, store.save_batch(payload))
                if path == '/api/review':
                    record = payload.get('record')
                    if not isinstance(record, dict):
                        raise ValueError('记录格式不正确')
                    for field in EDITABLE_FIELDS:
                        if record.get(field) is not None and not isinstance(record[field], str):
                            raise ValueError('字段必须为文字: ' + field)
                    return self.send(200, {'record': review_record(record)})
                return self.send(404, {'error': '操作不存在'})
            except (ValueError, TypeError, KeyError):
                return self.send(400, {'error': '内容或设置格式不正确，请检查后重试'})
            except (OSError, sqlite3.Error):
                return self.send(500, {'error': '本地保存失败，请检查磁盘空间和文件权限'})

    return Handler


def create_server(port=8765, directory=None, config_path=None):
    store = LocalStore(Path(directory) if directory else ROOT / '.local-private' / 'software', config_path)
    return ThreadingHTTPServer(('127.0.0.1', port), make_handler(store))


def main():
    parser = argparse.ArgumentParser(description='报价工作台：本地粘贴、结构化、复核与保存')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = create_server(args.port)
    except OSError:
        server = create_server(0)
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'报价工作台已启动：{url}', flush=True)
    print('所有报价仅在本机处理。关闭此窗口或按 Ctrl+C 结束服务。', flush=True)
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
