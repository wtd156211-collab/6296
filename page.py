"""自包含只读 HTML 页面：列 x 候选类型热力图 + 分段条 + 冲突证据。

单文件、无外部引用、无网络请求；数据以 JSON 字面量内联，
与报告 JSON 完全一致；配色固定，页面不含时间戳等易变内容。
"""

import json

_PALETTE = {
    "bool": "#4e79a7",
    "int": "#59a14f",
    "float": "#f28e2b",
    "date": "#e15759",
    "text": "#9c755f",
}
_NULL_BG = "#e8e8e8"
_CONFLICT_RED = "#d62728"

_JS = r"""
const REPORT = __REPORT__;
const EVIDENCE = __EVIDENCE__;
const PALETTE = __PALETTE__;
const NULL_BG = '__NULL_BG__';
const CONFLICT_RED = '__CONFLICT_RED__';
const TYPES = ['bool', 'int', 'float', 'date', 'text'];

const PAD = 12, LABEL_W = 180, CELL_W = 64, GAP = 16, BAR_W = 320, TYPE_W = 90;
const ROW_H = 26, HEADER_H = 34;
const HEAT_X = PAD + LABEL_W;
const BAR_X = HEAT_X + CELL_W * TYPES.length + GAP;
const TYPE_X = BAR_X + BAR_W + GAP;
const WIDTH = TYPE_X + TYPE_W + PAD;

const conflictByColumn = {};
for (const c of REPORT.conflicts) conflictByColumn[c.column] = c;
let selected = -1;

const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');

function heatFill(col, t) {
  const counts = col.type_counts;
  const n = col.non_null_count;
  if (!counts[t] || n === 0) return null;
  const share = counts[t] / n;
  const conflict = conflictByColumn[col.name];
  if (conflict) {
    const ev = EVIDENCE[col.name];
    if (ev && t !== ev.dominant) return {color: CONFLICT_RED, alpha: 1};
  }
  return {color: PALETTE[t], alpha: 0.25 + 0.75 * share};
}

function draw() {
  const rows = REPORT.columns.length;
  canvas.width = WIDTH;
  canvas.height = HEADER_H + rows * ROW_H + PAD;
  ctx.font = '12px sans-serif';
  ctx.textBaseline = 'middle';

  ctx.fillStyle = '#666';
  ctx.textAlign = 'left';
  ctx.fillText('column', PAD, HEADER_H / 2);
  TYPES.forEach((t, i) => {
    ctx.fillText(t, HEAT_X + i * CELL_W + 6, HEADER_H / 2);
  });
  ctx.fillText('type counts (bar: non-null share)', BAR_X, HEADER_H / 2);

  REPORT.columns.forEach((col, r) => {
    const y = HEADER_H + r * ROW_H;
    if (r === selected) {
      ctx.fillStyle = '#fff3d6';
      ctx.fillRect(0, y, WIDTH, ROW_H);
    }
    ctx.fillStyle = '#222';
    ctx.textAlign = 'left';
    let name = col.name;
    while (name.length > 1 && ctx.measureText(name).width > LABEL_W - 8) {
      name = name.slice(0, -2);
    }
    if (name !== col.name) name = name.slice(0, -1) + '…';
    ctx.fillText(name, PAD, y + ROW_H / 2);

    TYPES.forEach((t, i) => {
      const x = HEAT_X + i * CELL_W;
      ctx.fillStyle = NULL_BG;
      ctx.fillRect(x + 1, y + 2, CELL_W - 2, ROW_H - 4);
      const fill = heatFill(col, t);
      if (fill) {
        ctx.globalAlpha = fill.alpha;
        ctx.fillStyle = fill.color;
        ctx.fillRect(x + 1, y + 2, CELL_W - 2, ROW_H - 4);
        ctx.globalAlpha = 1;
        const conflict = conflictByColumn[col.name];
        if (conflict && EVIDENCE[col.name] && t === EVIDENCE[col.name].dominant) {
          ctx.strokeStyle = '#333';
          ctx.lineWidth = 2;
          ctx.strokeRect(x + 2, y + 3, CELL_W - 4, ROW_H - 6);
        }
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.fillText(String(col.type_counts[t]), x + CELL_W / 2, y + ROW_H / 2);
        ctx.textAlign = 'left';
      }
    });

    ctx.fillStyle = NULL_BG;
    ctx.fillRect(BAR_X, y + 4, BAR_W, ROW_H - 8);
    const total = REPORT.row_count;
    if (total > 0 && col.non_null_count > 0) {
      const barW = BAR_W * col.non_null_count / total;
      let x = BAR_X;
      for (const t of TYPES) {
        const c = col.type_counts[t] || 0;
        if (!c) continue;
        const w = barW * c / col.non_null_count;
        ctx.fillStyle = PALETTE[t];
        ctx.fillRect(x, y + 4, w, ROW_H - 8);
        x += w;
      }
    }
    ctx.fillStyle = '#222';
    ctx.fillText(col.type, TYPE_X, y + ROW_H / 2);
  });
}

function renderEvidence() {
  const panel = document.getElementById('evidence');
  if (selected < 0) {
    panel.textContent = '点击左侧任意一行查看该列详情；冲突列会列出证据行。';
    return;
  }
  const col = REPORT.columns[selected];
  const conflict = conflictByColumn[col.name];
  let html = '<h3>' + esc(col.name) + ' → <code>' + esc(col.type) + '</code></h3>';
  html += '<p>非空 ' + col.non_null_count + ' / 空 ' + col.null_count +
    '；计数 ' + esc(JSON.stringify(col.type_counts)) + '</p>';
  if (!conflict) {
    html += '<p>该列无类型冲突。</p>';
  } else {
    const ev = EVIDENCE[col.name];
    html += '<p>主导类型 <code>' + esc(ev.dominant) + '</code>，类型组合 ' +
      esc(conflict.types.join(' + ')) + '，冲突值共 ' + conflict.evidence_count + ' 条' +
      (conflict.evidence_count > ev.rows.length ? '（仅列前 ' + ev.rows.length + ' 条）' : '') +
      '；行号为原文件数据行号（从 1 起、不含表头）。</p>';
    html += '<table><thead><tr><th>行号</th><th>原始值</th><th>格子类型</th></tr></thead><tbody>';
    for (const item of ev.rows) {
      html += '<tr><td>' + item.row + '</td><td>' + esc(item.value) + '</td><td>' +
        esc(item.cell_type) + '</td></tr>';
    }
    html += '</tbody></table>';
  }
  panel.innerHTML = html;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

canvas.addEventListener('click', e => {
  const rect = canvas.getBoundingClientRect();
  const r = Math.floor((e.clientY - rect.top - HEADER_H) / ROW_H);
  if (r >= 0 && r < REPORT.columns.length) {
    selected = (r === selected) ? -1 : r;
    draw();
    renderEvidence();
  }
});

function renderConflicts() {
  const box = document.getElementById('conflicts');
  if (!REPORT.conflicts.length) {
    box.innerHTML = '<p>无类型冲突。</p>';
    return;
  }
  let html = '<table><thead><tr><th>列名</th><th>类型组合</th><th>证据行</th></tr></thead><tbody>';
  for (const c of REPORT.conflicts) {
    const more = c.evidence_count > c.evidence_rows.length ?
      ' … 共 ' + c.evidence_count + ' 条' : '';
    html += '<tr><td>' + esc(c.column) + '</td><td>' + esc(c.types.join(' + ')) +
      '</td><td>' + c.evidence_rows.join(', ') + esc(more) + '</td></tr>';
  }
  box.innerHTML = html + '</tbody></table>';
}

draw();
renderConflicts();
renderEvidence();
"""

_CSS = """
body { font-family: sans-serif; margin: 24px; color: #222; }
h1 { font-size: 20px; }
h2 { font-size: 16px; margin-top: 28px; }
canvas { border: 1px solid #ddd; cursor: pointer; }
table { border-collapse: collapse; margin-top: 8px; }
th, td { border: 1px solid #ccc; padding: 4px 10px; font-size: 13px; text-align: left; }
th { background: #f5f5f5; }
.legend span { display: inline-block; margin-right: 14px; font-size: 13px; }
.legend i { display: inline-block; width: 12px; height: 12px; margin-right: 4px;
  vertical-align: -1px; }
#evidence { margin-top: 20px; }
.meta { color: #555; font-size: 13px; }
"""


def _json_literal(obj):
    """JSON 字面量，转义 `</` 防止闭合 script 标签。"""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def _html_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_html(report, evidence_payload):
    """根据报告与证据载荷生成自包含 HTML 文本（以 \\n 结尾）。"""
    legend_items = "".join(
        '<span><i style="background:%s"></i>%s</span>' % (color, name)
        for name, color in _PALETTE.items()
    )
    legend_items += (
        '<span><i style="background:%s"></i>null/空</span>' % _NULL_BG
        + '<span><i style="background:%s"></i>冲突（非主导类型）</span>' % _CONFLICT_RED
    )
    js = (_JS
          .replace("__REPORT__", _json_literal(report))
          .replace("__EVIDENCE__", _json_literal(evidence_payload))
          .replace("__PALETTE__", _json_literal(_PALETTE))
          .replace("__NULL_BG__", _NULL_BG)
          .replace("__CONFLICT_RED__", _CONFLICT_RED))
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>%s - 列类型报告</title>" % _html_escape(report["table"]),
        "<style>%s</style>" % _CSS,
        "</head>",
        "<body>",
        "<h1>列类型报告：%s</h1>" % _html_escape(report["table"]),
        '<p class="meta">数据行 %d，列 %d，冲突列 %d。'
        "热力图格深 = 该类型占非空格比例；红色格 = 冲突列中的非主导类型；"
        "右侧横条长按类型计数分段、总长与非空占比成比例，空值留底色。</p>"
        % (report["row_count"], report["column_count"], len(report["conflicts"])),
        '<p class="legend">%s</p>' % legend_items,
        '<canvas id="chart"></canvas>',
        '<div id="evidence"></div>',
        "<h2>冲突清单</h2>",
        '<div id="conflicts"></div>',
        "<script>%s</script>" % js,
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def write_html(report, evidence_payload, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(render_html(report, evidence_payload))
