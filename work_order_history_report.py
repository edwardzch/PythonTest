# -*- coding: utf-8 -*-
import os
import datetime
from utils import work_order_db
from utils.app_utils import get_app_base_path
import webbrowser

def format_duration(seconds):
    """格式化时长显示"""
    if seconds <= 0:
        return "-"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试序列历史数据汇总</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333; }}
        .container {{ max-width: 1800px; margin: 20px auto; padding: 20px; background-color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; text-align: center; }}
        .timestamp {{ text-align: right; color: #7f8c8d; font-size: 0.9em; margin-bottom: 20px; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 8px 6px; border: 1px solid #ddd; text-align: center; font-size: 0.85em; }}
        th {{ background-color: #3498db; color: white; white-space: nowrap; }}
        th.meal {{ background-color: #27ae60; font-size: 0.9em; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #eaf2f8; }}
        
        .pass-rate {{ font-weight: bold; }}
        .high-rate {{ color: #27ae60; }}
        .medium-rate {{ color: #f39c12; }}
        .low-rate {{ color: #c0392b; }}
        
        .toolbar {{ margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        .toolbar input {{ padding: 8px 12px; width: 300px; border: 1px solid #ccc; border-radius: 4px; }}
        .toolbar button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
        .btn-search {{ background-color: #3498db; color: white; }}
        .btn-search:hover {{ background-color: #2980b9; }}
        .btn-export {{ background-color: #27ae60; color: white; }}
        .btn-export:hover {{ background-color: #1e8449; }}
        .btn-clear {{ background-color: #95a5a6; color: white; }}
        .btn-clear:hover {{ background-color: #7f8c8d; }}
        
        .info-box {{ background-color: #ecf0f1; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 30px; flex-wrap: wrap; }}
        .stats-item {{ text-align: center; min-width: 80px; }}
        .stats-value {{ font-size: 1.4em; font-weight: bold; color: #2c3e50; }}
        .stats-label {{ font-size: 0.85em; color: #7f8c8d; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>测试序列历史数据汇总</h1>
        <div class="timestamp">生成时间: {gen_time}</div>
        
        <div class="info-box">
            <div class="stats-item">
                <div class="stats-value">{total_sessions}</div>
                <div class="stats-label">测试会话数</div>
            </div>
            <div class="stats-item">
                <div class="stats-value">{total_pass}</div>
                <div class="stats-label">总Pass数</div>
            </div>
            <div class="stats-item">
                <div class="stats-value">{total_fail}</div>
                <div class="stats-label">总Fail数</div>
            </div>
            <div class="stats-item">
                <div class="stats-value">{avg_pass_rate:.1f}%</div>
                <div class="stats-label">平均良率</div>
            </div>
        </div>
        
        <div class="toolbar">
            <input type="text" id="searchInput" placeholder="搜索序列名称或操作员..." onkeypress="if(event.keyCode==13)filterTable()">
            <button class="btn-search" onclick="filterTable()">🔍 查询</button>
            <button class="btn-clear" onclick="clearFilter()">清除筛选</button>
            <button class="btn-export" onclick="exportCSV()">📊 导出CSV</button>
        </div>
        
        <table id="woTable">
            <thead>
                <tr>
                    <th>日期</th>
                    <th>测试序列</th>
                    <th>工位数</th>
                    <th>操作员</th>
                    <th>Pass</th>
                    <th>Fail</th>
                    <th>良率</th>
                    <th>平均测试(s)</th>
                    <th>拿取耗时(s)</th>
                    <th>总耗时(实际)</th>
                    <th class="meal">午餐</th>
                    <th class="meal">晚餐</th>
                    <th>总耗时(工作)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable() {{
            var input = document.getElementById("searchInput");
            var filter = input.value.toUpperCase();
            var table = document.getElementById("woTable");
            var tr = table.getElementsByTagName("tr");

            for (var i = 1; i < tr.length; i++) {{
                var tds = tr[i].getElementsByTagName("td");
                var found = false;
                for (var j = 0; j < tds.length; j++) {{
                    var txtValue = tds[j].textContent || tds[j].innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                        found = true;
                        break;
                    }}
                }}
                tr[i].style.display = found ? "" : "none";
            }}
        }}
        
        function clearFilter() {{
            document.getElementById("searchInput").value = "";
            filterTable();
        }}
        
        function exportCSV() {{
            var table = document.getElementById("woTable");
            var rows = table.querySelectorAll("tr");
            var csvContent = "\\uFEFF";
            
            rows.forEach(function(row) {{
                if (row.style.display === "none") return;
                var cols = row.querySelectorAll("td, th");
                var rowData = [];
                cols.forEach(function(col) {{
                    var text = col.innerText.replace(/"/g, '""');
                    rowData.push('"' + text + '"');
                }});
                csvContent += rowData.join(",") + "\\n";
            }});
            
            var blob = new Blob([csvContent], {{ type: "text/csv;charset=utf-8;" }});
            var link = document.createElement("a");
            var url = URL.createObjectURL(blob);
            link.setAttribute("href", url);
            link.setAttribute("download", "测试序列历史数据_" + new Date().toISOString().slice(0,10) + ".csv");
            link.style.visibility = "hidden";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
    </script>
</body>
</html>
"""

def generate_and_open_history_report():
    """Generates an HTML report for all sessions and opens it."""
    
    # 1. Fetch Data using new session system
    sessions = work_order_db.get_all_sessions()
    
    # 2. Calculate Summary Stats
    total_sessions = len(sessions)
    total_pass = sum(s.get('pass_qty', 0) for s in sessions)
    total_fail = sum(s.get('fail_qty', 0) for s in sessions)
    total_tests = total_pass + total_fail
    avg_pass_rate = (total_pass / total_tests * 100) if total_tests > 0 else 0
    
    # 3. Build Rows
    rows_html = ""
    for session in sessions:
        session_id = session.get('id')
        seq_name = session.get('sequence_name', '-')
        session_date = session.get('session_date', '-')
        station_count = session.get('station_count', 1)
        operator_name = session.get('operator_name', '-')
        operator_id = session.get('operator_id', '')
        pass_qty = session.get('pass_qty', 0)
        fail_qty = session.get('fail_qty', 0)
        pass_rate = session.get('pass_rate', 0)
        avg_dur = session.get('avg_duration', 0)
        lunch_duration = session.get('lunch_duration', 60)
        dinner_duration = session.get('dinner_duration', 40)
        
        # 格式化操作员显示
        operator_display = f"{operator_name} ({operator_id})" if operator_id else (operator_name or "-")
        
        # 计算拿取耗时（使用会话记录的吃饭时长）
        handling_time = work_order_db.get_session_handling_time(session_id, lunch_duration, dinner_duration)
        
        # 计算两种总耗时
        actual_elapsed, work_elapsed = work_order_db.get_session_total_times(session_id, lunch_duration, dinner_duration)
        
        # Pass Rate Class
        rate_cls = "high-rate"
        if pass_rate < 90: rate_cls = "medium-rate"
        if pass_rate < 80: rate_cls = "low-rate"
            
        rows_html += f"""
        <tr>
            <td>{session_date}</td>
            <td style="text-align:left;">{seq_name}</td>
            <td>{station_count}</td>
            <td>{operator_display}</td>
            <td>{pass_qty}</td>
            <td>{fail_qty}</td>
            <td class="pass-rate {rate_cls}">{pass_rate:.1f}%</td>
            <td>{avg_dur:.2f}</td>
            <td>{handling_time:.1f}</td>
            <td>{format_duration(actual_elapsed)}</td>
            <td>{lunch_duration}分钟</td>
            <td>{dinner_duration}分钟</td>
            <td>{format_duration(work_elapsed)}</td>
        </tr>
        """

    # 4. Fill Template
    html_content = HTML_TEMPLATE.format(
        gen_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_sessions=total_sessions,
        total_pass=total_pass,
        total_fail=total_fail,
        avg_pass_rate=avg_pass_rate,
        table_rows=rows_html
    )
    
    # 5. Save and Open
    try:
        report_dir = os.path.join(get_app_base_path(), "HistoryReports")
        os.makedirs(report_dir, exist_ok=True)
        
        filename = f"TestSessionHistory_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(report_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        webbrowser.open(f'file:///{os.path.abspath(filepath)}')
        return True, filepath
    except Exception as e:
        print(f"Failed to generate history report: {e}")
        return False, str(e)
