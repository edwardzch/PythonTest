# -*- coding: utf-8 -*-
"""
线缆管理对话框
类似顶针管理界面，整合线缆更换和线缆列表功能
"""
import os
import json
import datetime
import webbrowser
import csv

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QMessageBox, QComboBox, QSplitter, QGroupBox, QFormLayout,
    QAbstractItemView, QInputDialog, QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor

from consumable_manager import get_consumable_manager
from utils import consumable_db
from utils.app_utils import get_app_base_path


class CableManagementDialog(QDialog):
    """线缆管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = get_consumable_manager()
        self.parent_app = parent
        self.setWindowTitle("线缆管理")
        self.setMinimumSize(1000, 600)
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 顶部工具栏
        toolbar = QHBoxLayout()
        
        # 启用追踪开关
        self.enable_checkbox = QCheckBox("启用线缆追踪")
        self.enable_checkbox.setChecked(self._get_enabled_from_config())
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        toolbar.addWidget(self.enable_checkbox)
        
        toolbar.addSpacing(30)
        
        # 搜索框
        toolbar.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入线缆SN进行筛选...")
        self.search_input.textChanged.connect(self._filter_table)
        self.search_input.setMinimumWidth(300)
        toolbar.addWidget(self.search_input)
        
        toolbar.addStretch()
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(refresh_btn)
        
        # HTML报告按钮
        html_btn = QPushButton("📋 查看报告")
        html_btn.clicked.connect(self._generate_html)
        toolbar.addWidget(html_btn)
        
        main_layout.addLayout(toolbar)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：线缆表格
        left_widget = QGroupBox("线缆列表")
        left_layout = QVBoxLayout(left_widget)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["SN", "使用次数", "上限", "状态", "最后使用时间", "创建时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table)
        
        # 左侧按钮
        left_btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ 添加线缆")
        add_btn.clicked.connect(self._add_cable)
        left_btn_layout.addWidget(add_btn)
        
        retire_btn = QPushButton("❌ 标记报废")
        retire_btn.clicked.connect(self._retire_cable)
        left_btn_layout.addWidget(retire_btn)
        
        left_btn_layout.addStretch()
        
        left_layout.addLayout(left_btn_layout)
        splitter.addWidget(left_widget)
        
        # 右侧：线缆详情 & 更换
        right_widget = QGroupBox("线缆操作")
        right_layout = QVBoxLayout(right_widget)
        
        # 详情区
        detail_group = QGroupBox("选中线缆详情")
        detail_form = QFormLayout(detail_group)
        self.detail_sn = QLabel("-")
        self.detail_usage = QLabel("-")
        self.detail_limit = QLabel("-")
        self.detail_status = QLabel("-")
        
        detail_form.addRow("SN:", self.detail_sn)
        detail_form.addRow("使用次数:", self.detail_usage)
        detail_form.addRow("使用上限:", self.detail_limit)
        detail_form.addRow("状态:", self.detail_status)
        
        # 修改上限按钮
        edit_limit_btn = QPushButton("修改上限")
        edit_limit_btn.clicked.connect(self._edit_limit)
        detail_form.addRow("", edit_limit_btn)
        
        right_layout.addWidget(detail_group)
        
        right_layout.addStretch()
        
        # 更换区
        swap_group = QGroupBox("绑定线缆到工位")
        swap_layout = QFormLayout(swap_group)
        
        self.swap_station_combo = QComboBox()
        self.swap_station_combo.setMinimumWidth(200)
        if hasattr(self.parent(), 'station_frames'):
            # 使用实际的 station_id (小写 station_1 格式)
            for sid in self.parent().station_frames.keys():
                cable = self.manager.get_cable_for_station(sid)
                text = f"{sid}" if not cable else f"{sid} (当前: {cable})"
                self.swap_station_combo.addItem(text, sid)
        elif hasattr(self.parent(), 'global_config'):
            count = self.parent().global_config.get('station_count', 4)
            for i in range(count):
                sid = f"station_{i+1}"  # 小写格式
                cable = self.manager.get_cable_for_station(sid)
                text = f"{sid}" if not cable else f"{sid} (当前: {cable})"
                self.swap_station_combo.addItem(text, sid)
        swap_layout.addRow("工位:", self.swap_station_combo)
        
        self.new_sn_input = QLineEdit()
        self.new_sn_input.setPlaceholderText("扫描或输入线缆SN")
        swap_layout.addRow("线缆SN:", self.new_sn_input)
        
        swap_btn = QPushButton("✓ 确认绑定")
        swap_btn.clicked.connect(self._swap_cable)
        swap_layout.addRow("", swap_btn)
        
        right_layout.addWidget(swap_group)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # 底部关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn, alignment=Qt.AlignRight)
    
    def _load_data(self):
        """加载线缆数据"""
        self.table.setRowCount(0)
        cables = self.manager.get_all_cables()
        
        for cable in cables:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            sn = cable.get('sn', '')
            usage = cable.get('total_count', 0)
            limit = cable.get('max_limit', 10000)
            status = '报废' if cable.get('status') == 'retired' else '正常'
            last_seen = cable.get('last_seen_date', '-')[:10] if cable.get('last_seen_date') else '-'
            created = cable.get('created_at', '-')[:10] if cable.get('created_at') else '-'
            
            self.table.setItem(row, 0, QTableWidgetItem(sn))
            self.table.setItem(row, 1, QTableWidgetItem(str(usage)))
            self.table.setItem(row, 2, QTableWidgetItem(str(limit)))
            
            status_item = QTableWidgetItem(status)
            if status == '报废':
                status_item.setForeground(QColor('#e74c3c'))
            self.table.setItem(row, 3, status_item)
            
            self.table.setItem(row, 4, QTableWidgetItem(last_seen))
            self.table.setItem(row, 5, QTableWidgetItem(created))
        
        # 更新工位下拉框显示
        self._refresh_station_combo()
    
    def _refresh_station_combo(self):
        """刷新工位下拉框"""
        for i in range(self.swap_station_combo.count()):
            sid = self.swap_station_combo.itemData(i)
            cable = self.manager.get_cable_for_station(sid)
            text = f"{sid}" if not cable else f"{sid} (当前: {cable})"
            self.swap_station_combo.setItemText(i, text)
    
    def _filter_table(self, text):
        """筛选表格"""
        for row in range(self.table.rowCount()):
            sn_item = self.table.item(row, 0)
            match = text.lower() in sn_item.text().lower() if sn_item else True
            self.table.setRowHidden(row, not match)
    
    def _on_selection_changed(self):
        """选中行变化"""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        
        row = rows[0].row()
        sn = self.table.item(row, 0).text()
        usage = self.table.item(row, 1).text()
        limit = self.table.item(row, 2).text()
        status = self.table.item(row, 3).text()
        
        self.detail_sn.setText(sn)
        self.detail_usage.setText(usage)
        self.detail_limit.setText(limit)
        self.detail_status.setText(status)
    
    def _add_cable(self):
        """添加新线缆"""
        sn, ok = QInputDialog.getText(self, "添加线缆", "输入线缆SN:")
        if ok and sn:
            info = self.manager.check_cable_sn(sn)
            if info:
                QMessageBox.information(self, "成功", f"线缆 {sn} 已添加")
                self._load_data()
    
    def _edit_limit(self):
        """修改选中线缆的使用上限"""
        sn = self.detail_sn.text()
        if sn == "-":
            QMessageBox.warning(self, "提示", "请先选择一条线缆")
            return
        
        current_limit = self.detail_limit.text()
        try:
            current_limit = int(current_limit)
        except:
            current_limit = 10000
        
        from PySide6.QtWidgets import QSpinBox
        new_limit, ok = QInputDialog.getInt(
            self, "修改使用上限", 
            f"线缆 {sn} 的新使用上限:", 
            current_limit, 1, 999999, 1000
        )
        if ok:
            from utils import consumable_db
            consumable_db.update_cable_limit(sn, new_limit)
            self._load_data()
            self.detail_limit.setText(str(new_limit))
            QMessageBox.information(self, "成功", f"已将线缆 {sn} 的使用上限修改为 {new_limit}")
    
    def _retire_cable(self):
        """标记报废"""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "提示", "请先选择一条线缆")
            return
        
        sn = self.table.item(rows[0].row(), 0).text()
        reply = QMessageBox.question(self, "确认", f"确定要将线缆 {sn} 标记为报废吗？")
        if reply == QMessageBox.Yes:
            self.manager.retire_cable(sn)
            self._load_data()
    
    def _swap_cable(self):
        """绑定线缆到工位"""
        station_id = self.swap_station_combo.currentData()
        new_sn = self.new_sn_input.text().strip()
        
        if not new_sn:
            QMessageBox.warning(self, "提示", "请输入线缆SN")
            return
        
        success, msg = self.manager.bind_cable_to_station(station_id, new_sn)
        if success:
            QMessageBox.information(self, "成功", f"工位 {station_id} 已绑定线缆 {new_sn}")
            self.new_sn_input.clear()
            self._refresh_station_combo()
            self._load_data()  # 自动刷新列表
        else:
            QMessageBox.warning(self, "失败", msg)
    
    def _export_csv(self):
        """导出CSV"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出CSV", 
            os.path.join(get_app_base_path(), f"cables_{datetime.datetime.now().strftime('%Y%m%d')}.csv"),
            "CSV files (*.csv)"
        )
        if not filepath:
            return
        
        cables = self.manager.get_all_cables()
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["SN", "使用次数", "使用上限", "状态", "最后使用时间", "创建时间"])
            for cable in cables:
                writer.writerow([
                    cable.get('sn', ''),
                    cable.get('total_count', 0),
                    cable.get('max_limit', 10000),
                    '报废' if cable.get('status') == 'retired' else '正常',
                    cable.get('last_seen_date', ''),
                    cable.get('created_at', '')
                ])
        
        QMessageBox.information(self, "成功", f"已导出到 {filepath}")
    
    def _generate_html(self):
        """生成HTML报告（与顶针历史报告风格一致）"""
        cables = self.manager.get_all_cables()
        gen_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 生成表格行
        rows_html = ""
        for idx, cable in enumerate(cables, 1):
            status = '报废' if cable.get('status') == 'retired' else '正常'
            status_style = 'color: #e74c3c;' if status == '报废' else ''
            rows_html += f"""
            <tr>
                <td>{idx}</td>
                <td>{cable.get('sn', '-')}</td>
                <td>{cable.get('total_count', 0)}</td>
                <td>{cable.get('max_limit', 10000)}</td>
                <td style="{status_style}">{status}</td>
                <td>{(cable.get('last_seen_date') or '-')[:10]}</td>
                <td>{(cable.get('created_at') or '-')[:10]}</td>
            </tr>"""
        
        if not rows_html:
            rows_html = '<tr><td colspan="7" style="text-align:center; color:#7f8c8d; padding:50px;">暂无线缆记录</td></tr>'
        
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>线缆使用记录</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333; }}
        .container {{ max-width: 1400px; margin: 20px auto; padding: 20px; background-color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; text-align: center; }}
        .timestamp {{ text-align: right; color: #7f8c8d; font-size: 0.9em; margin-bottom: 10px; }}
        
        .toolbar {{ margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        .toolbar input {{ padding: 8px 12px; width: 300px; border: 1px solid #ccc; border-radius: 4px; }}
        .toolbar button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
        .btn-search {{ background-color: #3498db; color: white; }}
        .btn-search:hover {{ background-color: #2980b9; }}
        .btn-export {{ background-color: #27ae60; color: white; }}
        .btn-export:hover {{ background-color: #1e8449; }}
        .btn-clear {{ background-color: #95a5a6; color: white; }}
        .btn-clear:hover {{ background-color: #7f8c8d; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px 8px; border: 1px solid #ddd; text-align: center; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #eaf2f8; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>线缆使用记录</h1>
        <div class="timestamp">生成时间: {gen_time}</div>
        
        <div class="toolbar">
            <input type="text" id="searchInput" placeholder="搜索SN或状态..." onkeypress="if(event.keyCode==13)filterTable()">
            <button class="btn-search" onclick="filterTable()">🔍 查询</button>
            <button class="btn-clear" onclick="clearFilter()">清除筛选</button>
            <button class="btn-export" onclick="exportCSV()">📊 导出CSV</button>
        </div>
        
        <table id="cableTable">
            <thead>
                <tr>
                    <th>序号</th>
                    <th>SN</th>
                    <th>使用次数</th>
                    <th>使用上限</th>
                    <th>状态</th>
                    <th>最后使用时间</th>
                    <th>创建时间</th>
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
            var rows = document.getElementById('cableTable').getElementsByTagName('tr');
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
            var csv = '序号,SN,使用次数,使用上限,状态,最后使用时间,创建时间\\n';
            var rows = document.getElementById('cableTable').getElementsByTagName('tr');
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
            link.download = 'cables_export.csv';
            link.click();
        }}
    </script>
</body>
</html>"""
        
        # 保存文件
        reports_dir = os.path.join(get_app_base_path(), 'CableReports')
        os.makedirs(reports_dir, exist_ok=True)
        filepath = os.path.join(reports_dir, f"cables_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        webbrowser.open(f"file://{filepath}")
    
    def _get_enabled_from_config(self):
        """从配置文件读取启用状态"""
        if self.parent_app and hasattr(self.parent_app, 'global_config'):
            tracking_config = self.parent_app.global_config.get('cable_tracking', {})
            return tracking_config.get('enabled', True)
        return True
    
    def _on_enable_changed(self, state):
        """保存启用状态到配置文件"""
        enabled = bool(state)  # state > 0 means checked
        if self.parent_app and hasattr(self.parent_app, 'global_config'):
            if 'cable_tracking' not in self.parent_app.global_config:
                self.parent_app.global_config['cable_tracking'] = {}
            self.parent_app.global_config['cable_tracking']['enabled'] = enabled
            
            # 保存到文件
            try:
                config_path = os.path.join(get_app_base_path(), 'config.json')
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.parent_app.global_config, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")
