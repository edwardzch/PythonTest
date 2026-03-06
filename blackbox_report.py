# blackbox_report.py
"""
黑匣子通讯日志报告生成器。
将测试板黑匣子记录解析并渲染为美观的 HTML 报告。

通道标签定义:
  [A] = FCT上位机 → 测试板 (Modbus 发送帧)
  [a] = 测试板 → FCT上位机 (Modbus 响应帧)
  [B] = 测试板 → 编码器 (DMA 发送帧)
  [b] = 编码器 → 测试板 (DMA 接收帧)
  [*] = 内部事件 / 自定义日志
"""

import os
import re
from datetime import datetime

# 通道配置: 标签 -> (显示名称, 颜色, 方向描述)
CHANNEL_CONFIG = {
    'A': ('FCT→板端', '#4A90D9', 'Modbus TX (上位机发送)'),
    'a': ('板端→FCT', '#5BC0DE', 'Modbus RX (板端响应)'),
    'B': ('板端→编码器', '#F0AD4E', '编码器 DMA TX'),
    'b': ('编码器→板端', '#5CB85C', '编码器 DMA RX'),
    '*': ('内部事件', '#9B59B6', '板端日志'),
}

# 解析日志行的正则: [00001][A][+00003346ms] 05 06 10 00 00 07 CD 4C
LINE_PATTERN = re.compile(
    r'\[(\d+)\]'           # [序号]
    r'\[([ABab*])\]'       # [通道标签]
    r'\[\+(\d+)ms\]'       # [+时间戳ms]
    r'\s+(.*)'             # 数据内容
)


def parse_line(line):
    """解析单行黑匣子日志，自动剥离可能的 [RX] <- 或 [TX] -> 前缀"""
    # 剥离可能的 [RX] <- 或 [TX] -> 前缀
    stripped = line.strip()
    if '<-' in stripped:
        stripped = stripped.split('<-', 1)[1].strip()
    elif '->' in stripped:
        stripped = stripped.split('->', 1)[1].strip()
    
    m = LINE_PATTERN.match(stripped)
    if m:
        return {
            'seq': int(m.group(1)),
            'channel': m.group(2),
            'time_ms': int(m.group(3)),
            'data': m.group(4).strip()
        }
    return None


def generate_blackbox_report(lines, uut_sn, station_id, report_dir, overflow=False):
    """
    生成黑匣子 HTML 报告。
    
    :param lines: 原始日志行列表
    :param uut_sn: 产品SN
    :param station_id: 工位ID
    :param report_dir: 报告保存目录
    :param overflow: 是否有记录溢出
    :return: 报告文件绝对路径
    """
    # 解析所有日志行
    records = []
    unparsed_lines = []
    for line in lines:
        parsed = parse_line(line)
        if parsed:
            records.append(parsed)
        else:
            unparsed_lines.append(line)
    
    # 统计信息
    channel_counts = {}
    for r in records:
        ch = r['channel']
        channel_counts[ch] = channel_counts.get(ch, 0) + 1
    
    total_records = len(records)
    time_span_ms = records[-1]['time_ms'] - records[0]['time_ms'] if records else 0
    time_span_s = time_span_ms / 1000.0
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    station_short = station_id.replace('station_', 'S')
    # 清理SN中的非法文件名字符 (Windows不允许 \ / : * ? " < > |)
    safe_sn = re.sub(r'[\\/:*?"<>|]', '_', uut_sn)
    filename = f"BlackBox_{station_short}_{safe_sn}_{timestamp}.html"
    
    # 确保报告目录存在
    os.makedirs(report_dir, exist_ok=True)
    filepath = os.path.join(report_dir, filename)
    
    try:
        # 生成统计卡片 HTML
        stats_html = _generate_stats_html(total_records, channel_counts, time_span_s, overflow)
        
        # 生成日志表格 HTML
        table_html = _generate_table_html(records)
        
        # 渲染完整 HTML
        html = HTML_TEMPLATE.format(
            title=f"黑匣子报告 - {uut_sn}",
            uut_sn=uut_sn,
            station_id=station_id,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_records=total_records,
            overflow_badge='<span class="badge badge-danger">⚠ 记录溢出</span>' if overflow else '<span class="badge badge-ok">正常</span>',
            stats_cards=stats_html,
            log_table=table_html,
        )
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"[BlackBox] 报告已生成: {filepath} ({total_records} 条记录, {len(unparsed_lines)} 条未解析)")
        
    except Exception as e:
        # 如果生成失败，删除可能的空文件
        print(f"[BlackBox] 报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(filepath) and os.path.getsize(filepath) == 0:
            os.remove(filepath)
        raise
    
    return os.path.abspath(filepath)


def _generate_stats_html(total, channel_counts, time_span_s, overflow):
    """生成统计卡片"""
    cards = []
    cards.append(f'''
        <div class="stat-card">
            <div class="stat-value">{total}</div>
            <div class="stat-label">总记录数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{time_span_s:.2f}s</div>
            <div class="stat-label">时间跨度</div>
        </div>
    ''')
    
    for ch, (name, color, _) in CHANNEL_CONFIG.items():
        count = channel_counts.get(ch, 0)
        if count > 0:
            cards.append(f'''
                <div class="stat-card">
                    <div class="stat-value" style="color:{color}">{count}</div>
                    <div class="stat-label">[{ch}] {name}</div>
                </div>
            ''')
    
    return '\n'.join(cards)


def _generate_table_html(records):
    """生成日志表格"""
    rows = []
    for r in records:
        ch = r['channel']
        cfg = CHANNEL_CONFIG.get(ch, ('未知', '#999', ''))
        name, color, desc = cfg
        
        rows.append(f'''
            <tr class="channel-{ch}">
                <td class="seq">{r['seq']:05d}</td>
                <td><span class="channel-tag" style="background:{color}">[{ch}]</span> {name}</td>
                <td class="time">+{r['time_ms']}ms</td>
                <td class="data">{r['data']}</td>
            </tr>
        ''')
    
    return '\n'.join(rows)


# ==================== HTML 模板 ====================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: #0f1923;
            color: #c7d5e0;
            padding: 20px;
        }}
        
        /* 报告头部 */
        .report-header {{
            background: linear-gradient(135deg, #1a2a3a, #243447);
            border-radius: 12px;
            padding: 24px 32px;
            margin-bottom: 20px;
            border: 1px solid #2a4055;
        }}
        .report-header h1 {{
            font-size: 24px;
            color: #e8edf2;
            margin-bottom: 12px;
        }}
        .report-header h1 .icon {{ font-size: 28px; margin-right: 8px; }}
        .header-info {{
            display: flex;
            gap: 32px;
            flex-wrap: wrap;
            font-size: 14px;
            color: #8899aa;
        }}
        .header-info span {{ display: inline-flex; align-items: center; gap: 6px; }}
        .header-info .label {{ color: #667788; }}
        .header-info .value {{ color: #c7d5e0; font-weight: 600; }}
        
        /* 徽章 */
        .badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-ok {{ background: #1a4731; color: #5CB85C; }}
        .badge-danger {{ background: #4a1a1a; color: #e74c3c; }}
        
        /* 统计卡片 */
        .stats-container {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #1a2a3a;
            border: 1px solid #2a4055;
            border-radius: 10px;
            padding: 16px 24px;
            min-width: 120px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: 700;
            color: #e8edf2;
        }}
        .stat-label {{
            font-size: 12px;
            color: #667788;
            margin-top: 4px;
        }}
        
        /* 通道图例 */
        .legend {{
            background: #1a2a3a;
            border: 1px solid #2a4055;
            border-radius: 10px;
            padding: 16px 24px;
            margin-bottom: 20px;
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}
        
        /* 日志表格 */
        .log-container {{
            background: #1a2a3a;
            border: 1px solid #2a4055;
            border-radius: 10px;
            overflow: hidden;
        }}
        .log-container h2 {{
            padding: 16px 24px;
            font-size: 16px;
            color: #e8edf2;
            border-bottom: 1px solid #2a4055;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        thead th {{
            background: #243447;
            color: #8899aa;
            padding: 10px 16px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
        }}
        tbody tr {{
            border-bottom: 1px solid #1e3042;
            transition: background 0.15s;
        }}
        tbody tr:hover {{
            background: #1e3348;
        }}
        td {{
            padding: 8px 16px;
        }}
        .seq {{
            color: #667788;
            font-family: 'Consolas', monospace;
            font-size: 12px;
        }}
        .time {{
            color: #8899aa;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            white-space: nowrap;
        }}
        .data {{
            font-family: 'Consolas', 'Courier New', monospace;
            color: #e8edf2;
            word-break: break-all;
        }}
        .channel-tag {{
            display: inline-block;
            padding: 1px 6px;
            border-radius: 4px;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            min-width: 24px;
            text-align: center;
        }}
        
        /* 滚动容器 */
        .table-scroll {{
            max-height: 70vh;
            overflow-y: auto;
        }}
        .table-scroll::-webkit-scrollbar {{ width: 8px; }}
        .table-scroll::-webkit-scrollbar-track {{ background: #1a2a3a; }}
        .table-scroll::-webkit-scrollbar-thumb {{ background: #3a5065; border-radius: 4px; }}
        .table-scroll::-webkit-scrollbar-thumb:hover {{ background: #4a6075; }}
        
        /* 页脚 */
        .footer {{
            text-align: center;
            padding: 16px;
            color: #4a5568;
            font-size: 12px;
        }}
        
        @media print {{
            body {{ background: #fff; color: #333; padding: 10px; }}
            .report-header {{ background: #f5f5f5; border-color: #ddd; }}
            .report-header h1 {{ color: #333; }}
            .stat-card, .legend, .log-container {{ background: #fff; border-color: #ddd; }}
            .table-scroll {{ max-height: none; overflow: visible; }}
            thead th {{ background: #f0f0f0; color: #555; }}
            tbody tr:hover {{ background: transparent; }}
            .data {{ color: #333; }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1><span class="icon">📦</span>黑匣子通讯日志报告</h1>
        <div class="header-info">
            <span><span class="label">产品SN:</span> <span class="value">{uut_sn}</span></span>
            <span><span class="label">工位:</span> <span class="value">{station_id}</span></span>
            <span><span class="label">时间:</span> <span class="value">{timestamp}</span></span>
            <span><span class="label">记录数:</span> <span class="value">{total_records}</span></span>
            <span><span class="label">状态:</span> {overflow_badge}</span>
        </div>
    </div>
    
    <div class="stats-container">
        {stats_cards}
    </div>
    
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:#4A90D9"></div> [A] FCT→板端 (Modbus TX)</div>
        <div class="legend-item"><div class="legend-dot" style="background:#5BC0DE"></div> [a] 板端→FCT (Modbus RX)</div>
        <div class="legend-item"><div class="legend-dot" style="background:#F0AD4E"></div> [B] 板端→编码器 (DMA TX)</div>
        <div class="legend-item"><div class="legend-dot" style="background:#5CB85C"></div> [b] 编码器→板端 (DMA RX)</div>
        <div class="legend-item"><div class="legend-dot" style="background:#9B59B6"></div> [*] 内部事件</div>
    </div>
    
    <div class="log-container">
        <h2>📋 通讯日志 ({total_records} 条)</h2>
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th style="width:70px">序号</th>
                        <th style="width:160px">通道</th>
                        <th style="width:120px">时间戳</th>
                        <th>数据</th>
                    </tr>
                </thead>
                <tbody>
                    {log_table}
                </tbody>
            </table>
        </div>
    </div>
    
    <div class="footer">
        黑匣子通讯日志报告 | 自动生成于 {timestamp}
    </div>
</body>
</html>'''
