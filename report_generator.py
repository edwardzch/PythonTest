# 文件路径: report_generator.py (100%完整最终修复版)
# -*- coding: utf-8 -*-

import os
import datetime
import base64
from collections import Counter
from io import BytesIO

try:
    import matplotlib.pyplot as plt
    import matplotlib

    matplotlib.use('Agg')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    import numpy as np

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("警告: Matplotlib 或 Numpy 未安装，无法生成图表和CPK分析。")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>循环压力测试报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333; }}
        .container {{ max-width: 1200px; margin: 20px auto; padding: 20px; background-color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; }}
        h1, h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h1 {{ text-align: center; }}
        h3 {{ color: #34495e; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background-color: #ecf0f1; padding: 20px; border-radius: 5px; text-align: center; }}
        .summary-card h3 {{ margin-top: 0; }}
        .summary-card .value {{ font-size: 2em; font-weight: bold; color: #2980b9; }}
        .summary-card .value.pass {{ color: #27ae60; }}
        .summary-card .value.fail {{ color: #c0392b; }}
        .chart-container, .station-analysis {{ margin-bottom: 30px; padding: 20px; background: #ecf0f1; border-radius: 5px; }}
        .chart-container {{ text-align: center; }}
        .station-charts-container {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; }}
        .station-chart-item {{ flex-basis: 48%; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .status-pass {{ color: #27ae60; font-weight: bold; }}
        .status-fail {{ color: #c0392b; font-weight: bold; }}
        .details-toggle {{ cursor: pointer; color: #3498db; text-decoration: underline; }}
        .details-row {{ display: none; }}
        .details-content {{ background-color: #fdf2e9; padding: 15px; }}
        .details-content pre {{ white-space: pre-wrap; word-wrap: break-word; background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #eee;}}
    </style>
</head>
<body>
    <div class="container">
        <h1>循环压力测试报告</h1>
        <h2>测试概览</h2>
        <div class="summary-grid">{summary_cards}</div>
        <div class="chart-container">
            <h2>失败项总体分析</h2>
            {fail_chart}
        </div>
        <div class="station-analysis">
            <h2>各工位失败项分析</h2>
            {station_fail_analysis}
        </div>
        {cpk_section}
        <h2>详细测试记录</h2>
        <div class="extra-info" style="background-color: #e8f6f3; padding: 10px; margin-bottom: 20px; border-radius: 5px; border-left: 5px solid #1abc9c;">
            <p style="margin: 5px 0;"><strong>测试软件版本:</strong> {app_version}</p>
            <p style="margin: 5px 0;"><strong>顶针使用次数:</strong> {thimble_usage}</p>
        </div>
        <table>
            <thead>
                <tr><th>#</th><th>工位</th><th>产品SN</th><th>操作员工号</th><th>开始时间</th><th>耗时(s)</th><th>结果</th><th>详情</th></tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>
    <script>
        function toggleDetails(rowId) {{
            var row = document.getElementById(rowId);
            if (row.style.display === "none") {{ row.style.display = "table-row"; }} else {{ row.style.display = "none"; }}
        }}
    </script>
</body>
</html>
"""


class ReportGenerator:
    def __init__(self, results_data, config):
        self.results = results_data
        self.config = config
        self.start_time = datetime.datetime.now()

    def _create_pie_chart(self, title, data_counter):
        if not MATPLOTLIB_AVAILABLE or not data_counter:
            return ""

        labels = list(data_counter.keys())
        sizes = list(data_counter.values())

        def value_format(pct):
            total = sum(sizes)
            absolute = int(round(pct / 100. * total))
            return f"{absolute}次\n({pct:.1f}%)"

        fig, ax = plt.subplots(figsize=(8, 5))
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct=value_format,
                                          startangle=90, wedgeprops=dict(width=0.4), pctdistance=0.75)

        plt.setp(autotexts, size=8, weight="bold", color="white")
        ax.axis('equal')
        plt.title(title, pad=20, fontsize=14)

        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        encoded_string = base64.b64encode(buf.read()).decode('utf-8')
        return f'<img src="data:image/png;base64,{encoded_string}" alt="{title}" style="max-width:100%; height:auto;">'

    def _generate_summary_cards(self, stats):
        cards_html = ""
        card_items = [
            ("总循环次数", stats['total_runs'], ""),
            ("成功次数", stats['pass_count'], "pass"),
            ("失败次数", stats['fail_count'], "fail"),
            ("成功率", f"{stats['pass_rate']:.2f}%", "pass" if stats['pass_rate'] > 90 else "fail"),
            ("总耗时", f"{stats['total_duration']:.2f}s", ""),
            ("平均耗时", f"{stats['avg_duration']:.2f}s", ""),
        ]
        for title, value, value_class in card_items:
            cards_html += f"""
            <div class="summary-card">
                <h3>{title}</h3>
                <p class="value {value_class}">{value}</p>
            </div>
            """
        return cards_html

    def _generate_fail_chart(self, fail_details):
        if not fail_details: return "<p>无失败项，无需分析。</p>"

        fail_steps = [d.get('step_name', '未知步骤') for d in fail_details if isinstance(d, dict)]
        if not fail_steps: return "<p>失败项中未找到有效的步骤信息。</p>"

        fail_counts = Counter(fail_steps)
        return self._create_pie_chart("失败步骤总体分布", fail_counts)

    def _generate_station_fail_analysis(self):
        station_fails = {}
        for result in self.results:
            if result.get('status') == 'FAIL':
                station_id = str(result.get('station_id', 'N/A')).split('_')[-1]
                fail_details = result.get('fail_details')
                if not isinstance(fail_details, dict): continue

                if station_id not in station_fails:
                    station_fails[station_id] = Counter()

                step_name = fail_details.get('step_name', '未知步骤')
                station_fails[station_id][step_name] += 1

        if not station_fails:
            return "<p>所有工位均无失败项。</p>"

        charts_html = ""
        for station_id, fail_counts in sorted(station_fails.items()):
            chart_title = f"工位 {station_id} 失败统计"
            pie_chart_img = self._create_pie_chart(chart_title, fail_counts)
            if pie_chart_img:
                charts_html += f'<div class="station-chart-item">{pie_chart_img}</div>'

        return f'<div class="station-charts-container">{charts_html}</div>' if charts_html else "<p>无法为各工位生成失败图表。</p>"

    # --- 【【【 已补全：_generate_table_rows 方法 】】】 ---
    def _generate_table_rows(self):
        rows_html = ""
        for i, result in enumerate(self.results):
            status_class = "status-pass" if result['status'] == 'PASS' else "status-fail"
            start_time_str = result.get('start_time', 'N/A')
            if isinstance(start_time_str, datetime.datetime):
                start_time_str = start_time_str.strftime('%H:%M:%S')

            details_row_id = f"details_{i}"
            details_button = ""
            details_row_html = ""

            if result['status'] == "FAIL" and isinstance(result.get('fail_details'), dict):
                details = result['fail_details']
                
                # Extract boolean from tuple for display, similar to UI logic
                result_value = details.get('result', 'N/A')
                if isinstance(result_value, tuple) and len(result_value) >= 2 and isinstance(result_value[0], bool):
                    result_display = str(result_value[0])  # Show only True/False
                else:
                    result_display = str(result_value)
                
                details_button = f'<span class="details-toggle" onclick="toggleDetails(\'{details_row_id}\')">查看</span>'
                details_row_html = f"""
                <tr id="{details_row_id}" class="details-row">
                    <td colspan="7">
                        <div class="details-content">
                            <strong>失败详情:</strong>
                            <pre>步骤: {details.get('step_name', 'N/A')}
结果: {result_display}
信息: {details.get('message', 'N/A')}</pre>
                        </div>
                    </td>
                </tr>
                """

            rows_html += f"""
            <tr>
                <td>{result.get('cycle', i + 1)}</td>
                <td>{str(result.get('station_id', 'N/A')).split('_')[-1]}</td>
                <td>{result.get('sn', 'N/A')}</td>
                <td>{result.get('operator_id', 'N/A')}</td> <!-- NEW -->
                <td>{start_time_str}</td>
                <td>{result.get('duration', 0.0):.2f}</td>
                <td class="{status_class}">{result.get('status', 'N/A')}</td>
                <td>{details_button}</td>
            </tr>
            {details_row_html}
            """
        return rows_html

    def generate_report(self):
        # 1. 数据分析
        total_runs = len(self.results)
        pass_count = sum(1 for r in self.results if r['status'] == 'PASS')
        fail_count = total_runs - pass_count
        pass_rate = (pass_count / total_runs * 100) if total_runs > 0 else 0.0
        total_duration = sum(r.get('duration', 0.0) for r in self.results)
        avg_duration = (total_duration / total_runs) if total_runs > 0 else 0.0
        fail_details = [r['fail_details'] for r in self.results if r['status'] == 'FAIL' and r.get('fail_details')]
        
        # NEW: CPK data aggregation by station
        cpk_data_by_station = {}
        selected_cpk_steps = self.config.get("cpk_steps", [])
        
        for r in self.results:
            station_id = str(r.get('station_id', 'N/A')).split('_')[-1]
            if station_id not in cpk_data_by_station:
                cpk_data_by_station[station_id] = {step_name: {'values': [], 'usl': None, 'lsl': None} for step_name in selected_cpk_steps}

            for step_name in selected_cpk_steps:
                if step_name in r.get('cpk_values', {}):
                    step_data = r['cpk_values'][step_name]
                    if isinstance(step_data, dict):
                        value = step_data.get('value')
                        if isinstance(value, (int, float)):
                            data_bundle = cpk_data_by_station[station_id][step_name]
                            data_bundle['values'].append(value)
                            # Only set USL/LSL once per step per station, assuming they are constant
                            if data_bundle['usl'] is None: data_bundle['usl'] = step_data.get('usl')
                            if data_bundle['lsl'] is None: data_bundle['lsl'] = step_data.get('lsl')

        stats = {"total_runs": total_runs, "pass_count": pass_count, "fail_count": fail_count, "pass_rate": pass_rate,
                 "total_duration": total_duration, "avg_duration": avg_duration}

        # 2. 渲染HTML
        summary_cards_html = self._generate_summary_cards(stats)
        fail_chart_html = self._generate_fail_chart(fail_details)
        station_fail_analysis_html = self._generate_station_fail_analysis()
        cpk_section_html = self._generate_cpk_section(cpk_data_by_station) # Pass new structure
        table_rows_html = self._generate_table_rows()

        html_content = HTML_TEMPLATE.format(
            summary_cards=summary_cards_html,
            fail_chart=fail_chart_html,
            station_fail_analysis=station_fail_analysis_html,
            cpk_section=cpk_section_html,
            app_version=self.config.get('app_version', 'N/A'),
            thimble_usage=self.config.get('thimble_usage_info', 'N/A'),
            table_rows=table_rows_html
        )

        # 3. 保存文件
        try:
            main_report_path = self.config.get('main_report_path')
            if not main_report_path:
                base_dir = "CycleTestReports"
                date_dir = os.path.join(base_dir, self.start_time.strftime('%Y-%m-%d'))
                main_report_path = os.path.join(date_dir, f"Report_{self.start_time.strftime('%Y%m%d_%H%M%S')}")
                os.makedirs(main_report_path, exist_ok=True)

            filename = f"Summary_Report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.html"
            filepath = os.path.join(main_report_path, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            return filepath
        except Exception as e:
            print(f"生成报告失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # --- 【【【 已补全：_generate_cpk_section 方法 】】】 ---
    def _generate_cpk_section(self, cpk_data_by_station): # Updated signature
        if not self.config.get("cpk_steps") or not cpk_data_by_station:
            return ""

        if not MATPLOTLIB_AVAILABLE:
            return "<h2>CPK 分析</h2><p>Numpy 未安装，无法进行CPK计算。</p>"

        def calculate_cpk(data, usl, lsl):
            if not data or usl is None or lsl is None: return "N/A", "N/A", "N/A", "N/A"

            mean = np.mean(data)
            std = np.std(data, ddof=1) if len(data) > 1 else 0

            if std == 0: return mean, std, "Infinity", "Infinity"

            cp = (usl - lsl) / (6 * std)
            cpk = min((usl - mean) / (3 * std), (mean - lsl) / (3 * std))

            return mean, std, cp, cpk

        full_cpk_html = "<h2>CPK 分析</h2>"

        # --- NEW: All Stations Summary ---
        all_stations_data = {}
        for station_id, cpk_data_for_station in cpk_data_by_station.items():
            for step_name, data_bundle in cpk_data_for_station.items():
                if not data_bundle['values']: continue
                
                if step_name not in all_stations_data:
                    all_stations_data[step_name] = {'values': [], 'usl': data_bundle['usl'], 'lsl': data_bundle['lsl']}
                
                all_stations_data[step_name]['values'].extend(data_bundle['values'])

        if all_stations_data:
            full_cpk_html += "<h3>所有工位汇总 CPK 分析</h3>"
            table_html = "<table><thead><tr><th>参数</th><th>USL</th><th>LSL</th><th>Mean (μ)</th><th>Std Dev (σ)</th><th>Cp</th><th>Cpk</th></tr></thead><tbody>"
            
            for step_name, data_bundle in all_stations_data.items():
                try:
                    usl = data_bundle.get('usl')
                    lsl = data_bundle.get('lsl')
                    numeric_values = [v for v in data_bundle.get('values', []) if isinstance(v, (int, float))]
                    
                    mean, std, cp, cpk = calculate_cpk(numeric_values, usl, lsl)

                    mean_str = f"{mean:.4f}" if isinstance(mean, float) else str(mean)
                    std_str = f"{std:.4f}" if isinstance(std, float) else str(std)
                    cp_str = f"{cp:.4f}" if isinstance(cp, float) else str(cp)
                    cpk_str = f"{cpk:.4f}" if isinstance(cpk, float) else str(cpk)

                    table_html += f"<tr><td>{step_name}</td><td>{usl}</td><td>{lsl}</td><td>{mean_str}</td><td>{std_str}</td><td>{cp_str}</td><td>{cpk_str}</td></tr>"
                except Exception as e:
                    table_html += f"<tr><td>{step_name}</td><td colspan='6'>无法计算CPK (内部错误: {e})</td></tr>"
            
            table_html += "</tbody></table>"
            full_cpk_html += table_html
        # ---------------------------------
        
        # Sort by station_id for consistent report order
        for station_id, cpk_data_for_station in sorted(cpk_data_by_station.items()):
            # Filter out steps that have no data for this station
            valid_cpk_data = {k: v for k, v in cpk_data_for_station.items() if v['values']}
            if not valid_cpk_data:
                continue

            full_cpk_html += f"<h3>工位 {station_id} CPK 分析</h3>"
            table_html = "<table><thead><tr><th>参数</th><th>USL</th><th>LSL</th><th>Mean (μ)</th><th>Std Dev (σ)</th><th>Cp</th><th>Cpk</th></tr></thead><tbody>"

            for step_name, data_bundle in valid_cpk_data.items():
                try:
                    usl = data_bundle.get('usl')
                    lsl = data_bundle.get('lsl')

                    numeric_values = [v for v in data_bundle.get('values', []) if isinstance(v, (int, float))]

                    mean, std, cp, cpk = calculate_cpk(numeric_values, usl, lsl)

                    mean_str = f"{mean:.4f}" if isinstance(mean, float) else str(mean)
                    std_str = f"{std:.4f}" if isinstance(std, float) else str(std)
                    cp_str = f"{cp:.4f}" if isinstance(cp, float) else str(cp)
                    cpk_str = f"{cpk:.4f}" if isinstance(cpk, float) else str(cpk)

                    table_html += f"<tr><td>{step_name}</td><td>{usl}</td><td>{lsl}</td><td>{mean_str}</td><td>{std_str}</td><td>{cp_str}</td><td>{cpk_str}</td></tr>"

                except Exception as e:
                    table_html += f"<tr><td>{step_name}</td><td colspan='6'>无法计算CPK (内部错误: {e})</td></tr>"

            table_html += "</tbody></table>"
            full_cpk_html += table_html
            
        return full_cpk_html if full_cpk_html != "<h2>CPK 分析</h2>" else ""

