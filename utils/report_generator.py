import pandas as pd
from datetime import datetime
from string import Template

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>自动化测试报告 - ${uut_sn}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif; margin: 0; padding: 40px; background-color: #ffffff; color: #333; font-size: 14px; }
        .container { max-width: 1400px; margin: auto; }
        h1 { font-size: 24px; font-weight: 600; color: #2c3e50; text-align: center; margin-bottom: 40px; }
        .summary-table { width: auto; margin-bottom: 30px; border-collapse: collapse; margin-left: 0; margin-right: auto; }
        .summary-table td { padding: 6px 0; vertical-align: top; }
        .summary-table td.label { font-weight: 600; padding-right: 10px; color: #34495e; text-align: left; white-space: nowrap; }
        .summary-table td.value { text-align: left; }
        .status-pass { color: #27ae60; font-weight: bold; }
        .status-fail { color: #c0392b; font-weight: bold; }
        .status-user_stopped { color: #7f8c8d; font-weight: bold; }
        hr { border: none; border-top: 1px solid #ecf0f1; margin: 30px 0; }
        h2 { font-size: 18px; font-weight: 600; color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; margin-bottom: 20px; }
        .details-table { width: 100%; border-collapse: collapse; margin-top: 20px; table-layout: fixed; }
        .details-table th, .details-table td { border: 1px solid #ddd; padding: 10px; text-align: left; word-wrap: break-word; overflow-wrap: break-word; }
        .details-table th { background-color: #34495e; color: white; font-weight: normal; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .step-pass { color: #27ae60; }
        .step-fail { color: #c0392b; font-weight: bold; }
        .step-skipped { color: #7f8c8d; }
        .block-row { background-color: #bdc3c7 !important; font-weight: bold; text-align: center; }
        .flow-control { font-style: italic; color: #34495e; }
    </style>
</head>
<body>
    <div class="container">
        <h1>自动化测试报告</h1>
        <table class="summary-table">
            <tbody>
                <tr><td class="label">产品型号:</td><td class="value">${product_model}</td></tr>
                <tr><td class="label">测试程序版本:</td><td class="value">${sequence_version}</td></tr>
                <tr><td class="label">产品SN:</td><td class="value">${uut_sn}</td></tr>
                <tr><td class="label">工位号:</td><td class="value">${station_id}</td></tr>
                <tr><td class="label">转接线编码:</td><td class="value">${adapter_cables}</td></tr>
                <tr><td class="label">转接线寿命:</td><td class="value">${adapter_cable_life}</td></tr>
                <tr><td class="label">顶针使用寿命:</td><td class="value">${thimble_life}</td></tr>
                <tr><td class="label">操作员工号:</td><td class="value">${operator_id}</td></tr>
                <tr><td class="label">测试时间:</td><td class="value">${start_time}</td></tr>
                <tr><td class="label">测试用时:</td><td class="value">${duration_seconds}s</td></tr>
                <tr><td class="label">测试结果:</td><td class="value ${final_status_class}">${final_status}</td></tr>
                ${failure_details_row}
            </tbody>
        </table>
        <hr>
        <h2>测试详情</h2>
        <table class="details-table">
            <thead>
                <tr>
                    <th style="width: 4%;">步骤</th><th style="width: 15%;">测试名称</th><th style="width: 9%;">模块</th>
                    <th style="width: 9%;">函数</th><th style="width: 17%;">参数</th><th style="width: 6%;">比较</th><th style="width: 6%;">范围</th>
                    <th style="width: 4%;">状态</th><th style="width: 12%;">结果值</th><th style="width: 18%;">信息</th>
                </tr>
            </thead>
            <tbody>${table_rows}</tbody>
        </table>
    </div>
</body>
</html>
"""

def save_html_report(engine, filepath, final_status, final_message, duration):
    if filepath is None:
        engine.logger.error("由于未能生成有效的报告文件路径，HTML报告的保存操作被中止。")
        return

    failure_details_row_html = ""
    try:
        if final_status == "FAIL":
            fail_details = final_message.get('fail_details', {}) if isinstance(final_message, dict) else {}
            fail_msg = fail_details.get('message', '未知错误')
            step_index = fail_details.get('step_index', -1)
            step_name = ""
            if step_index != -1:
                try:
                    step_name = engine.sequence_df.loc[engine.sequence_df['original_index'] == step_index, 'TestName'].iloc[0] + " - "
                except (KeyError, IndexError):
                    pass
            full_fail_message = f"{step_name}{fail_msg}"
            failure_details_row_html = f"<tr><td class=\"label\">失败详情:</td><td class=\"value status-fail\">{full_fail_message}</td></tr>"

        table_rows = []
        indent_level = 0
        for step in engine.all_step_results_for_report:
            test_name, func_name = step.get('TestName', ''), step.get('Function', '')

            # 计算当前行的缩进
            current_indent = indent_level
            if func_name in ['elseif_variable', 'else_block', 'end_if', 'end_for']:
                current_indent = max(0, indent_level - 1)

            if step.get('type') == 'block' or test_name.startswith(('*', '#')):
                block_name = test_name.strip('*# ').strip()
                table_rows.append(f'<tr class="block-row"><td colspan="10">{block_name}</td></tr>')
                # 主要的区块标题重置缩进
                if block_name.lower() in ['setup', 'main', 'cleanup']: indent_level = 0
                continue

            display_test_name = test_name
            if func_name == 'if_variable':
                display_test_name = f"<span class='flow-control'>IF ({step.get('result', '')})</span>"
            elif func_name == 'elseif_variable':
                display_test_name = f"<span class='flow-control'>ELSE IF ({step.get('result', '')})</span>"
            elif func_name == 'else_block':
                display_test_name = f"<span class='flow-control'>ELSE</span>"
            elif func_name == 'end_if':
                display_test_name = f"<span class='flow-control'>END IF</span>"
            elif func_name == 'for_loop':
                display_test_name = f"<span class='flow-control'>FOR ({step.get('result', '')})</span>"
            elif func_name == 'end_for':
                display_test_name = f"<span class='flow-control'>END FOR ({step.get('result', '')})</span>"
            elif func_name == 'break_loop':
                display_test_name = f"<span class='flow-control'>BREAK</span>"

            status = step.get('status', 'SKIP').upper()
            status_class = f'step-{status.lower()}'
            limits = f"[{step.get('LowerLimit', '')}, {step.get('UpperLimit', '')}]" if step.get('LowerLimit') or step.get('UpperLimit') else ""
            compare_mode = step.get('Compare', '')
            display_step_num = '' if pd.isna(step_num_val := step.get('step_number')) else int(step_num_val)
            padding_left = 10 + current_indent * 25
            
            # Extract boolean from tuple for display, similar to UI logic
            result_value = step.get('result', '')
            if isinstance(result_value, tuple) and len(result_value) >= 2 and isinstance(result_value[0], bool):
                result_display = str(result_value[0])  # Show only True/False
            else:
                result_display = str(result_value)

            row = f"""<tr class="{status_class}">
                <td>{display_step_num}</td><td style="padding-left: {padding_left}px;">{display_test_name}</td>
                <td>{step.get('Module', '')}</td><td>{func_name}</td><td>{step.get('Parameters', '')}</td><td>{compare_mode}</td><td>{limits}</td>
                <td>{status}</td><td>{result_display}</td><td>{step.get('message', '')}</td></tr>"""
            table_rows.append(row)

            # 为下一行准备新的缩进级别
            if func_name in ['if_variable', 'for_loop']:
                indent_level += 1
            elif func_name in ['end_if', 'end_for']:
                indent_level = max(0, indent_level - 1)

        adapter_cables_val = getattr(engine, 'adapter_cables', None)
        if isinstance(adapter_cables_val, list) and adapter_cables_val and adapter_cables_val != ["Not used"]:
            adapter_cables_str = ", ".join(adapter_cables_val)
        elif isinstance(adapter_cables_val, str) and adapter_cables_val and adapter_cables_val not in ["N/A", ""]:
            adapter_cables_str = adapter_cables_val
        else:
            adapter_cables_str = "Not used"

        adapter_cable_life_val = getattr(engine, 'adapter_cable_life', None)
        if not adapter_cable_life_val or str(adapter_cable_life_val).strip() in ["N/A", "", "None"]:
            adapter_cable_life_str = "Not used"
        else:
            adapter_cable_life_str = str(adapter_cable_life_val)

        thimble_life_val = getattr(engine, 'thimble_life', None)
        if not thimble_life_val or str(thimble_life_val).strip() in ["N/A", "", "None"]:
            thimble_life_str = "Not used"
        else:
            thimble_life_str = str(thimble_life_val)

        template = Template(HTML_TEMPLATE)
        final_html = template.substitute(
            product_model=engine.product_model, sequence_version=engine.sequence_version, uut_sn=engine.uut_sn,
            station_id=engine.station_id, final_status=final_status.upper(),
            final_status_class=f'status-{final_status.lower()}',
            duration_seconds=round(duration, 2),
            start_time=datetime.fromtimestamp(engine.start_time).strftime('%Y-%m-%d %H:%M:%S'),
            table_rows=''.join(table_rows), failure_details_row=failure_details_row_html,
            operator_id=engine.operator_id if engine.operator_id else "N/A",
            adapter_cables=adapter_cables_str,
            adapter_cable_life=adapter_cable_life_str,
            thimble_life=thimble_life_str)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)
        engine.logger.info(f"HTML 测试报告已保存至: {filepath}")
    except Exception as e:
        engine.logger.error("保存 HTML 测试报告失败！", exc_info=True)
