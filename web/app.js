'use strict';

const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
const state = {batch: null, previous: null, base: {}, demo: '', edited: false, stale: false, sequence: 0, changes: 0, saving: false, inspected: null, timer: null, revisions: new Map(), reviews: new Set()};
const columns = [
  ['action', '本方动作', ['待确认', '买入', '卖出', '非本方']],
  ['bond_code', '债券代码'], ['bond_name', '债券简称'],
  ['business_type', '业务类型', ['普通报价', '回推要素', '组合/架桥']], ['amount_wan', '面额（万元）'],
  ['quote_price', '报价价格'], ['price_type', '价格类型', ['', '净价', '全价']],
  ['rate', '收益率（%）'], ['agreement_no', '约定号'], ['counterparty', '对手方'], ['requirements_text', '内评／授信'],
  ['workflow_status', '工作状态', ['待核对', '已保存未提交', '已提交']], ['notes_text', '备注'],
  ['seller', '卖方', null, true], ['buyer', '买方', null, true],
  ['trade_date', '交易日期', null, true], ['settlement_date', '结算日期', null, true],
  ['settlement_speed', '结算速度', null, true], ['term', '剩余期限', null, true],
  ['yield_type', '收益率类型', ['', '行权', '到期'], true], ['request_to', '请求发送至', null, true],
  ['contacts_text', '联系人', null, true],
  ['theoretical_price', '理论价格', null, true], ['adjustment_amount', '附注金额（元）', null, true]
];
const labels = Object.fromEntries(columns.map(c => [c[0], c[1]]));
const numeric = new Set(['amount_wan', 'quote_price', 'rate', 'theoretical_price', 'adjustment_amount']);

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function message(text) { $('message').textContent = text; $('message').hidden = !text; }
function error(text) { $('error').textContent = text; $('error').hidden = !text; }
async function request(path, payload) {
  let response;
  try {
    response = await fetch(path, payload === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Local-App': 'quote-workbench'}, body: JSON.stringify(payload)
    });
  } catch (_) { throw new Error('无法连接本地服务。请保持启动窗口开启，或重新双击“启动软件.cmd”。'); }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败，请重试。');
  return result;
}
function fillSettings(settings) {
  state.base = clone(settings);
  $('self-company').value = settings.self_company || '';
  $('self-aliases').value = (settings.self_aliases || []).join('，');
  $('to-direction').value = settings.to_direction;
  $('amount-unit').value = settings.default_amount_unit || '';
  $('k-unit').value = settings.k_multiplier_wan || '';
  $('rate-is-yield').checked = !!settings.unlabeled_rate_is_yield;
}
function readSettings() {
  return {...state.base, self_company: $('self-company').value.trim(),
    self_aliases: $('self-aliases').value.split(/[,，、\n]/).map(s => s.trim()).filter(Boolean),
    to_direction: $('to-direction').value, default_amount_unit: $('amount-unit').value || null,
    k_multiplier_wan: $('k-unit').value || null, unlabeled_rate_is_yield: $('rate-is-yield').checked};
}
function sourceChanged() {
  $('character-count').textContent = `${$('quote-input').value.length.toLocaleString()} 字`;
  state.stale = true;
  state.sequence++;
  clearTimeout(state.timer);
  updateSummary();
  if (state.edited) {
    $('input-hint').textContent = '原文或口径已变更。点击“识别报价”应用变更；重新识别后可撤销。';
    updateSummary();
  } else {
    state.timer = setTimeout(() => parse(), 550);
  }
}
async function parse() {
  clearTimeout(state.timer);
  const seq = ++state.sequence;
  const button = $('parse-button'); button.disabled = true; button.textContent = '正在识别…';
  error('');
  try {
    const result = await request('/api/parse', {text: $('quote-input').value, settings: readSettings()});
    if (seq !== state.sequence) return;
    if (state.batch?.records.length) state.previous = clone(state.batch);
    result.original_records = clone(result.records);
    state.batch = result; state.edited = false; state.stale = false; state.inspected = null;
    $('inspector').hidden = true;
    $('input-hint').textContent = '粘贴后自动识别，也可按 Ctrl + Enter。';
    message(result.input_warnings.join(' '));
    render();
  } catch (err) { if (seq === state.sequence) error(err.message); }
  finally { button.disabled = false; button.textContent = '识别报价'; }
}
function filteredRows() {
  const search = $('search').value.trim().toLowerCase();
  return (state.batch?.records || []).filter(row =>
    (!$('action-filter').value || row.action === $('action-filter').value) &&
    (!$('review-only').checked || row.issues.length) &&
    (!search || ['bond_code', 'bond_name', 'counterparty', 'seller', 'buyer', 'notes_text'].some(key => String(row[key] || '').toLowerCase().includes(search)))
  );
}
function updateSummary() {
  const rows = state.batch?.records || [], visible = filteredRows();
  const pending = rows.filter(row => row.issues.length).length;
  $('result-summary').textContent = rows.length
    ? `共 ${rows.length} 笔 · 买入 ${rows.filter(r => r.action === '买入').length} · 卖出 ${rows.filter(r => r.action === '卖出').length} · 待复核 ${pending} 笔${visible.length !== rows.length ? ` · 显示 ${visible.length} 笔` : ''}${state.stale ? ' · 原文／口径变更尚未应用' : ''}${state.edited ? ' · 有未保存修改' : ''}`
    : (state.batch ? '未找到可识别报价，请检查输入格式。' : '粘贴报价后，结果会显示在这里。');
  for (const id of ['save-button', 'csv-button', 'json-button']) $(id).disabled = !rows.length || state.stale || state.reviews.size > 0 || state.saving;
  $('undo-button').hidden = !state.previous;
  $('applied-company').textContent = state.batch ? `本批本方：${state.batch.settings.self_company || '尚未设置'}。状态标记不会向交易系统提交。` : '工作状态由你标记，不会向交易系统提交。';
}
function rowClasses(tr, row) {
  tr.classList.toggle('is-saved', row.workflow_status === '已保存未提交');
  tr.classList.toggle('is-submitted', row.workflow_status === '已提交');
  tr.classList.toggle('is-selected', state.inspected === row.record_id);
}
function sourceButton(button, row) {
  button.textContent = row.issues.length ? `复核 ${row.issues.length} 项` : '查看原文';
  button.className = `source-button${row.issues.length ? ' needs-review' : ''}`;
  button.setAttribute('aria-label', `${row.record_id} ${button.textContent}`);
}
function decorateInput(input, row, key) {
  const field = key === 'rate' ? 'yield_percent' : key;
  input.classList.toggle('modified', row.manual_fields.includes(field));
  const invalid = row.issues.some(issue => issue.field === field || (key === 'rate' && issue.field === 'yield_candidate'));
  input.classList.toggle('invalid', invalid); input.setAttribute('aria-invalid', String(invalid));
  input.title = row.issues.filter(issue => issue.field === field).map(issue => issue.message).join('；');
}
function render() {
  const head = node('tr');
  for (const [key, label, , extra] of columns) {
    const th = node('th', key === 'bond_name' ? '债券简称／原文' : label, `cell-${key}${extra ? ' extra-field' : ''}`); th.scope = 'col'; head.append(th);
  }
  $('table-head').replaceChildren(head);
  const body = document.createDocumentFragment();
  for (const row of filteredRows()) {
    const tr = node('tr'); tr.dataset.id = row.record_id; rowClasses(tr, row);
    for (const [key, label, options, extra] of columns) {
      const td = node('td', undefined, `cell-${key}${extra ? ' extra-field' : ''}`);
      if (key === 'details') {
        const button = node('button'); sourceButton(button, row); button.addEventListener('click', () => inspect(row.record_id)); td.append(button);
      } else {
        const field = key === 'rate' ? 'yield_percent' : key;
        const input = node(options ? 'select' : 'input'); input.dataset.field = key;
        if (options) {
          const values = [...options]; if (row[field] && !values.includes(row[field])) values.push(row[field]);
          for (const value of values) { const option = node('option', value || '待确认'); option.value = value; input.append(option); }
        } else { input.type = 'text'; input.autocomplete = 'off'; input.spellcheck = false; }
        const value = key === 'rate' ? row.yield_percent ?? row.yield_candidate : key === 'business_type' ? row.business_type || (row.workflow_kind?.includes('回推') ? '回推要素' : '普通报价') : row[field];
        input.value = value || '';
        input.setAttribute('aria-label', `${row.record_id} ${label}`);
        if (numeric.has(key)) { input.inputMode = 'decimal'; input.classList.add('number'); }
        decorateInput(input, row, key);
        input.addEventListener(options ? 'change' : 'input', () => edit(row.record_id, field, input.value, tr));
        if (key === 'rate' && row.yield_candidate && !row.yield_percent) {
          const wrap = node('div', undefined, 'rate-wrap'); wrap.append(input);
          const confirm = node('button', '确认', 'rate-confirm'); confirm.title = '确认该数字表示收益率';
          confirm.setAttribute('aria-label', `${row.record_id} 确认为收益率`);
          confirm.addEventListener('click', async () => { await edit(row.record_id, 'yield_percent', input.value, tr); render(); });
          wrap.append(confirm); td.append(wrap, node('span', '候选值，含义待确认', 'rate-note'));
        } else td.append(input);
      }
      if (key === 'bond_name') {
        const source = node('button'); sourceButton(source, row);
        source.addEventListener('click', () => inspect(row.record_id)); td.append(source);
      }
      tr.append(td);
    }
    body.append(tr);
  }
  $('table-body').replaceChildren(body);
  const hasRows = !!state.batch?.records.length;
  $('empty-state').hidden = hasRows;
  $('quote-table').hidden = !hasRows;
  if (hasRows && !filteredRows().length) {
    const tr = node('tr'), td = node('td', '没有符合筛选条件的报价。'); td.colSpan = columns.length; tr.append(td); $('table-body').append(tr);
  }
  updateSummary();
}
async function edit(id, field, value, tr) {
  const batch = state.batch, row = batch.records.find(r => r.record_id === id);
  const before = row[field] ?? ''; const after = value.trim();
  if (String(before) === after && !(field === 'yield_percent' && row.yield_candidate)) return;
  row[field] = after || null;
  if (!row.manual_fields.includes(field)) row.manual_fields.push(field);
  if (field === 'yield_percent') { row.yield_candidate = null; if (!row.manual_fields.includes('yield_candidate')) row.manual_fields.push('yield_candidate'); }
  const last = row.audit[row.audit.length - 1];
  if (last?.field === field && Date.now() - Date.parse(last.time) < 2000) { last.after = after; last.time = new Date().toISOString(); }
  else row.audit.push({field, before, after, time: new Date().toISOString()});
  state.changes++;
  state.edited = true;
  const revision = (state.revisions.get(id) || 0) + 1; state.revisions.set(id, revision);
  const token = {}; state.reviews.add(token); updateSummary();
  try {
    const result = await request('/api/review', {record: clone(row)});
    if (state.batch !== batch || state.revisions.get(id) !== revision) return;
    Object.assign(row, result.record);
    rowClasses(tr, row);
    tr.querySelectorAll('[data-field]').forEach(input => decorateInput(input, row, input.dataset.field));
    const button = tr.querySelector('.source-button'); if (button) sourceButton(button, row);
    if (state.inspected === id) inspect(id, false);
    message('修改已校验。点击“保存本地”保留本次修改。');
  } catch (err) { error(err.message); }
  finally { state.reviews.delete(token); updateSummary(); }
}
function inspect(id, scroll = true) {
  const row = state.batch.records.find(r => r.record_id === id); if (!row) return;
  state.inspected = id; $('inspector').hidden = false;
  $('inspector-heading').textContent = `${row.record_id} · ${row.bond_name || '未命名报价'} · 原文核对`;
  $('source-text').textContent = `原文第 ${row.source_line_start}—${row.source_line_end} 行\n\n${row.raw_text}`;
  $('issue-list').replaceChildren(...(row.issues.length ? row.issues.map(issue => node('li', issue.message)) : [node('li', '当前未发现规则校验问题，仍可对照原文确认。')]));
  $('audit-list').replaceChildren(...(row.audit.length ? row.audit.map(item => node('li', `${labels[item.field] || item.field}：${item.before || '空'} → ${item.after || '空'} · ${new Date(item.time).toLocaleString()}`)) : [node('li', '尚无手工修改。')]));
  const evidence = document.createDocumentFragment();
  for (const [field, proof] of Object.entries(row.evidence)) evidence.append(node('dt', labels[field] || field), node('dd', `${proof.snippet}（${proof.method}）`));
  $('evidence-list').replaceChildren(evidence);
  $('trading-codes').textContent = row.trading_codes.map(item => `${item.institution || ''} ${item.raw_line}`).join('\n') || '原文无补充交易代码。';
  $('table-body').querySelectorAll('tr[data-id]').forEach(tr => rowClasses(tr, state.batch.records.find(r => r.record_id === tr.dataset.id)));
  if (scroll) $('inspector').scrollIntoView({behavior: 'auto', block: 'start'});
}
function historyOptions(batches) {
  $('history').replaceChildren(node('option', '打开本地保存批次'));
  $('history').firstChild.value = '';
  for (const batch of batches) { const option = node('option', `${new Date(batch.created_at).toLocaleString()} · ${batch.company || '未设置公司'} · ${batch.count} 笔`); option.value = batch.id; $('history').append(option); }
}
async function loadHistory() {
  if (!$('history').value) return;
  try {
    const batch = await request(`/api/batches/${$('history').value}`);
    if (state.batch) state.previous = clone(state.batch);
    state.sequence++; clearTimeout(state.timer);
    state.batch = batch; state.edited = false; state.stale = false;
    $('quote-input').value = batch.original_input; $('character-count').textContent = `${batch.original_input.length.toLocaleString()} 字`;
    fillSettings(batch.settings); $('inspector').hidden = true; render(); message('已打开本地保存的批次。再次保存会创建新版本。');
  } catch (err) { error(err.message); }
}
async function save() {
  if (state.saving) return;
  const batch = state.batch, changes = state.changes, sequence = state.sequence;
  state.saving = true; updateSummary(); error('');
  try {
    const saved = await request('/api/save', clone(batch));
    const unchanged = state.batch === batch && state.changes === changes && state.sequence === sequence;
    if (unchanged) { state.batch = saved; state.edited = false; }
    historyOptions((await request('/api/batches')).batches); render();
    message(unchanged ? '已保存到本机。黄色表示已保存未提交；蓝色由你手工标记。' : '已保存点击时的版本；保存期间的新修改仍保留在当前表格，请再次保存。');
  } catch (err) { error(err.message); } finally { state.saving = false; updateSummary(); }
}
function download(contents, extension, type) {
  const blob = new Blob([contents], {type}); const url = URL.createObjectURL(blob);
  const link = node('a'); link.href = url; link.download = `报价_${new Date().toISOString().replace(/[:.]/g, '-')}.${extension}`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  message(`已导出 ${extension.toUpperCase()}，包含当前全部 ${state.batch.records.length} 笔报价。`);
}
function exportCSV() {
  const fields = columns.filter(c => !['rate', 'details'].includes(c[0]));
  fields.push(['yield_percent', '收益率（%）'], ['yield_candidate', '待确认收益率候选'], ['issues', '复核事项'], ['raw_text', '该笔原文']);
  const cell = value => { let text = String(value ?? ''); if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text; return '"' + text.replace(/"/g, '""') + '"'; };
  const lines = [fields.map(c => cell(c[1])).join(',')];
  for (const row of state.batch.records) lines.push(fields.map(([field]) => cell(field === 'issues' ? row.issues.map(i => i.message).join('；') : row[field])).join(','));
  download('\uFEFF' + lines.join('\r\n'), 'csv', 'text/csv;charset=utf-8');
}
async function demo() {
  fillSettings({...state.base, self_company: '示例甲证券', self_aliases: ['示例甲']});
  $('quote-input').value = state.demo;
  $('character-count').textContent = `${state.demo.length.toLocaleString()} 字`;
  await parse(); message('当前为全虚构样例。样例公司仅应用于本批，不会自动覆盖本机默认设置。');
}

$('settings-toggle').addEventListener('click', () => { const open = $('settings-panel').hidden; $('settings-panel').hidden = !open; $('settings-toggle').setAttribute('aria-expanded', String(open)); });
$('quote-input').addEventListener('input', sourceChanged);
$('quote-input').addEventListener('keydown', event => { if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); parse(); } });
for (const id of ['self-company', 'self-aliases', 'to-direction', 'amount-unit', 'k-unit', 'rate-is-yield']) $(id).addEventListener(['self-company', 'self-aliases'].includes(id) ? 'input' : 'change', () => {
  if (id === 'self-company' && $('self-company').value.trim() !== state.base.self_company) $('self-aliases').value = '';
  sourceChanged();
});
$('parse-button').addEventListener('click', parse);
$('demo-button').addEventListener('click', demo); $('empty-demo').addEventListener('click', demo);
$('clear-button').addEventListener('click', () => { $('quote-input').value = ''; $('character-count').textContent = '0 字'; parse(); });
for (const id of ['action-filter', 'review-only']) $(id).addEventListener('change', render);
$('search').addEventListener('input', render);
$('expand-button').addEventListener('click', () => { const expanded = $('table-wrap').classList.toggle('show-extra'); $('expand-button').setAttribute('aria-pressed', String(expanded)); $('expand-button').textContent = expanded ? '收起补充要素' : '展开全部要素'; });
$('close-inspector').addEventListener('click', () => { $('inspector').hidden = true; state.inspected = null; render(); });
$('save-button').addEventListener('click', save); $('history').addEventListener('change', loadHistory);
$('csv-button').addEventListener('click', exportCSV);
$('json-button').addEventListener('click', () => download(JSON.stringify(state.batch, null, 2), 'json', 'application/json;charset=utf-8'));
$('undo-button').addEventListener('click', () => {
  if (!state.previous) return;
  const current = state.batch; state.batch = state.previous; state.previous = current; state.sequence++; clearTimeout(state.timer);
  $('quote-input').value = state.batch.original_input; $('character-count').textContent = `${state.batch.original_input.length.toLocaleString()} 字`;
  fillSettings(state.batch.settings); state.edited = true; state.stale = false; $('inspector').hidden = true; render(); message('已恢复上一批结果及修改。');
});
$('save-settings').addEventListener('click', async () => {
  try { const result = await request('/api/settings', {settings: readSettings()}); state.base = result.settings; message('已将识别口径保存为本机默认。'); }
  catch (err) { error(err.message); }
});
window.addEventListener('beforeunload', event => { if (state.edited) { event.preventDefault(); event.returnValue = ''; } });
async function bootstrap() {
  try { const result = await request('/api/bootstrap'); fillSettings(result.settings); state.demo = result.demo; historyOptions(result.batches); render(); }
  catch (err) { error(err.message); }
}
bootstrap();
