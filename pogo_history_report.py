# -*- coding: utf-8 -*-
"""
顶针历史报告生成器
生成HTML格式的顶针重置历史报告，支持搜索和CSV导出
"""
import os
import datetime
import webbrowser

from utils import consumable_db
from utils.app_utils import get_app_base_path


def format_datetime(iso_string):
    """格式化ISO日期时间字符串"""
    if not iso_string:
        return "-"
    try:
        dt = datetime.datetime.fromisoformat(iso_string)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return iso_string


def generate_pogo_history_html():
    """
    生成顶针历史HTML报告
    返回: (success, file_path or error_message)
    """
    try:
        history = consumable_db.get_all_pogo_history()
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 生成表格行
        rows_html = ""
        for idx, record in enumerate(history, 1):
            rows_html += f"""
            <tr>
                <td>{idx}</td>
                <td>{record.get('station_id', '-')}</td>
                <td>{record.get('fixture_code', '-')}</td>
                <td>{format_datetime(record.get('reset_time'))}</td>
                <td>{record.get('count_before_reset', 0)}</td>
                <td>{format_datetime(record.get('first_use_time'))}</td>
                <td>{record.get('operator_id', '-')}</td>
                <td>{record.get('notes', '-')}</td>
            </tr>"""
        
        if not rows_html:
            rows_html = '<tr><td colspan="8" style="text-align:center; color:#7f8c8d; padding:50px;">暂无顶针更换记录</td></tr>'
        
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>顶针更换历史记录</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333; }}
        .container {{ max-width: 1400px; margin: 20px auto; padding: 20px; background-color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #9b59b6; padding-bottom: 10px; text-align: center; }}
        .timestamp {{ text-align: right; color: #7f8c8d; font-size: 0.9em; margin-bottom: 10px; }}
        
        .toolbar {{ margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        .toolbar input {{ padding: 8px 12px; width: 300px; border: 1px solid #ccc; border-radius: 4px; }}
        .toolbar button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
        .btn-search {{ background-color: #9b59b6; color: white; }}
        .btn-search:hover {{ background-color: #8e44ad; }}
        .btn-export {{ background-color: #27ae60; color: white; }}
        .btn-export:hover {{ background-color: #1e8449; }}
        .btn-clear {{ background-color: #95a5a6; color: white; }}
        .btn-clear:hover {{ background-color: #7f8c8d; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px 8px; border: 1px solid #ddd; text-align: center; }}
        th {{ background-color: #9b59b6; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #eaf2f8; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>顶针更换历史记录</h1>
        <div class="timestamp">生成时间: {gen_time}</div>
        
        <div class="toolbar">
            <input type="text" id="searchInput" placeholder="搜索工位、治具编码或操作员..." onkeypress="if(event.keyCode==13)filterTable()">
            <button class="btn-search" onclick="filterTable()">🔍 查询</button>
            <button class="btn-clear" onclick="clearFilter()">清除筛选</button>
            <button class="btn-export" onclick="exportCSV()">📊 导出CSV</button>
        </div>
        
        <table id="pogoTable">
            <thead>
                <tr>
                    <th>序号</th>
                    <th>工位</th>
                    <th>治具编码</th>
                    <th>重置时间</th>
                    <th>重置前使用次数</th>
                    <th>首次使用时间</th>
                    <th>操作员</th>
                    <th>备注</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    
    <script>
        function filterTable() {{
            var input = document.getElementById('searchInput').value.toLowerCase();
            var rows = document.getElementById('pogoTable').getElementsByTagName('tr');
            for (var i = 1; i < rows.length; i++) {{
                var cells = rows[i].cells;
                var match = false;
                for (var j = 0; j < cells.length; j++) {{
                    if (cells[j].textContent.toLowerCase().includes(input)) {{
                        match = true;
                        break;
                    }}
                }}
                rows[i].style.display = match ? '' : 'none';
            }}
        }}
        
        function clearFilter() {{
            document.getElementById('searchInput').value = '';
            filterTable();
        }}
        
        function exportCSV() {{
            var csv = '序号,工位,治具编码,重置时间,重置前使用次数,首次使用时间,操作员,备注\\n';
            var rows = document.getElementById('pogoTable').getElementsByTagName('tr');
            for (var i = 1; i < rows.length; i++) {{
                if (rows[i].style.display !== 'none') {{
                    var cells = rows[i].cells;
                    var rowData = [];
                    for (var j = 0; j < cells.length; j++) {{
                        rowData.push(cells[j].textContent);
                    }}
                    csv += rowData.join(',') + '\\n';
                }}
            }}
            var blob = new Blob([csv], {{type: 'text/csv;charset=utf-8;'}});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'pogo_history_export.csv';
            link.click();
        }}
    </script>
</body>
</html>"""
        
        # 保存文件
        reports_dir = os.path.join(get_app_base_path(), 'PogoHistoryReports')
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = f"pogo_history_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(reports_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return True, filepath
        
    except Exception as e:
        return False, str(e)


def generate_and_open_pogo_history():
    """生成并打开顶针历史报告"""
    success, result = generate_pogo_history_html()
    if success:
        webbrowser.open(f"file://{result}")
        return True, result
    else:
        return False, result
