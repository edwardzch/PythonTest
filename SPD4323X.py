import wx
import wx.lib.buttons as buttons  # 引入通用按钮库，用于自定义颜色
import pyvisa
import time

# ===============================================================================
# 全局配色方案 (暗黑仪表风)
# ===============================================================================
THEME = {
    'bg_main': wx.Colour(43, 43, 43),  # 主窗口深灰背景
    'bg_panel': wx.Colour(60, 63, 65),  # 通道面板背景
    'bg_lcd': wx.Colour(20, 20, 20),  # LCD 显示区全黑
    'text_lcd_v': wx.Colour(0, 255, 255),  # 电压青色
    'text_lcd_i': wx.Colour(0, 255, 0),  # 电流绿色
    'text_label': wx.Colour(200, 200, 200),  # 普通标签灰白
    'text_header': wx.Colour(255, 165, 0),  # 标题橙色
    'btn_set': wx.Colour(70, 130, 180),  # 设置按钮蓝
    'btn_off': wx.Colour(100, 100, 100),  # 关断状态灰
    'btn_on': wx.Colour(46, 204, 113),  # 开启状态绿
    'input_bg': wx.Colour(80, 80, 80),  # 输入框背景
    'input_fg': wx.Colour(255, 255, 255),  # 输入框文字
}


# ===============================================================================
# 驱动层 (保持不变，功能核心)
# ===============================================================================
class SPD4323X_Driver:
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = None
        self.connected = False

    def list_resources(self):
        try:
            return self.rm.list_resources()
        except:
            return []

    def connect(self, resource_id):
        try:
            self.inst = self.rm.open_resource(resource_id)
            self.inst.timeout = 2000
            self.inst.write_termination = '\n'
            self.inst.read_termination = '\n'
            idn = self.inst.query("*IDN?")
            self.connected = True
            return True, idn.strip()
        except Exception as e:
            self.connected = False
            return False, str(e)

    def close(self):
        if self.inst:
            try:
                self.inst.close()
            except:
                pass
        self.connected = False

    def set_voltage(self, ch, val):
        if self.connected: self.inst.write(f"SOUR:VOLT:SET CH{ch},{val}")

    def set_current(self, ch, val):
        if self.connected: self.inst.write(f"SOUR:CURR:SET CH{ch},{val}")

    def set_ovp(self, ch, val):
        if self.connected: self.inst.write(f"SOUR:OVP CH{ch},{val}")

    def set_ocp(self, ch, val):
        if self.connected: self.inst.write(f"SOUR:OCP CH{ch},{val}")

    def set_ocp_state(self, ch, state):
        val = 1 if state else 0
        if self.connected: self.inst.write(f"SOUR:OCP:STAT CH{ch},{val}")

    def set_output(self, ch, state):
        val = 1 if state else 0
        if self.connected: self.inst.write(f"OUTP CH{ch},{val}")

    def get_status(self, ch):
        if not self.connected: return 0.0, 0.0, "---"
        try:
            v = float(self.inst.query(f"MEAS:VOLT? CH{ch}"))
            i = float(self.inst.query(f"MEAS:CURR? CH{ch}"))
            mode = self.inst.query(f"MEAS:RUN:MODE? CH{ch}").strip()
            return v, i, mode
        except:
            return 0.0, 0.0, "ERR"


# ===============================================================================
# 自定义 UI 控件 (为了美观)
# ===============================================================================
class ModernButton(buttons.GenButton):
    """自定义颜色的扁平按钮"""

    def __init__(self, parent, label, size=(-1, -1), bg_color=THEME['btn_set']):
        super().__init__(parent, label=label, size=size)
        self.SetBackgroundColour(bg_color)
        self.SetForegroundColour(wx.WHITE)
        self.SetFont(wx.Font(9, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.SetBezelWidth(0)  # 扁平化
        self.SetUseFocusIndicator(False)


class DarkTextCtrl(wx.TextCtrl):
    """暗色输入框"""

    def __init__(self, parent, value, size):
        super().__init__(parent, value=value, size=size, style=wx.TE_PROCESS_ENTER | wx.BORDER_SIMPLE)
        self.SetBackgroundColour(THEME['input_bg'])
        self.SetForegroundColour(THEME['input_fg'])


# ===============================================================================
# 核心面板: 单通道控制
# ===============================================================================
class ChannelPanel(wx.Panel):
    def __init__(self, parent, channel_id, driver):
        super().__init__(parent)
        self.channel_id = channel_id
        self.driver = driver
        self.is_on = False

        self.SetBackgroundColour(THEME['bg_panel'])

        # --- 布局 ---
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 1. 标题头
        header = wx.StaticText(self, label=f"CHANNEL {channel_id}")
        header.SetFont(wx.Font(12, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        header.SetForegroundColour(THEME['text_header'])
        main_sizer.Add(header, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # 2. LCD 显示区 (黑底)
        lcd_panel = wx.Panel(self)
        lcd_panel.SetBackgroundColour(THEME['bg_lcd'])
        lcd_sizer = wx.FlexGridSizer(2, 2, 5, 10)

        # 标签
        lbl_v = wx.StaticText(lcd_panel, label="V:")
        lbl_v.SetForegroundColour(THEME['text_label'])
        lbl_i = wx.StaticText(lcd_panel, label="I:")
        lbl_i.SetForegroundColour(THEME['text_label'])

        # 读数
        self.read_v = wx.StaticText(lcd_panel, label="0.000")
        self.read_v.SetFont(wx.Font(24, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.read_v.SetForegroundColour(THEME['text_lcd_v'])

        self.read_i = wx.StaticText(lcd_panel, label="0.000")
        self.read_i.SetFont(wx.Font(24, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.read_i.SetForegroundColour(THEME['text_lcd_i'])

        lcd_sizer.Add(lbl_v, 0, wx.ALIGN_CENTER_VERTICAL)
        lcd_sizer.Add(self.read_v, 0, wx.ALIGN_RIGHT)
        lcd_sizer.Add(lbl_i, 0, wx.ALIGN_CENTER_VERTICAL)
        lcd_sizer.Add(self.read_i, 0, wx.ALIGN_RIGHT)

        lcd_wrapper = wx.BoxSizer(wx.VERTICAL)
        lcd_wrapper.Add(lcd_sizer, 1, wx.ALIGN_CENTER | wx.ALL, 10)

        # 模式显示
        self.lbl_mode = wx.StaticText(lcd_panel, label="MODE: ---")
        self.lbl_mode.SetForegroundColour(wx.Colour(100, 100, 100))
        lcd_wrapper.Add(self.lbl_mode, 0, wx.ALIGN_RIGHT | wx.RIGHT, 5)

        lcd_panel.SetSizer(lcd_wrapper)
        main_sizer.Add(lcd_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        main_sizer.AddSpacer(10)

        # 3. 参数设置区
        grid = wx.FlexGridSizer(4, 3, 8, 8)  # 行, 列, 间距

        # Helper to add row
        def add_row(label, default_val, handler):
            st = wx.StaticText(self, label=label)
            st.SetForegroundColour(THEME['text_label'])
            grid.Add(st, 0, wx.ALIGN_CENTER_VERTICAL)

            txt = DarkTextCtrl(self, value=default_val, size=(60, 25))
            txt.Bind(wx.EVT_TEXT_ENTER, handler)
            grid.Add(txt, 0)

            btn = ModernButton(self, "Set", size=(40, 25))
            btn.Bind(wx.EVT_BUTTON, handler)
            grid.Add(btn, 0)
            return txt

        self.txt_v = add_row("Volt (V):", "5.0", self.on_set_v)
        self.txt_i = add_row("Curr (A):", "1.0", self.on_set_i)

        # 分割线
        line = wx.StaticLine(self, size=(150, 1))
        line.SetBackgroundColour(wx.WHITE)  # Trick for dark theme lines
        main_sizer.Add(grid, 0, wx.ALIGN_CENTER)
        main_sizer.AddSpacer(10)

        # OVP/OCP 小字显示
        grid_prot = wx.FlexGridSizer(2, 3, 5, 5)
        self.txt_ovp = add_row("OVP (V):", "32.0", self.on_set_ovp)
        self.txt_ocp = add_row("OCP (A):", "3.2", self.on_set_ocp)
        main_sizer.Add(grid_prot, 0, wx.ALIGN_CENTER)

        main_sizer.AddSpacer(10)

        # OCP Mode Checkbox
        self.chk_ocp = wx.CheckBox(self, label=" OCP Cut-Off")
        self.chk_ocp.SetForegroundColour(THEME['text_label'])
        self.chk_ocp.SetToolTip("Checked: Cuts output at limit\nUnchecked: CC Mode")
        self.chk_ocp.Bind(wx.EVT_CHECKBOX, self.on_chk_ocp)
        main_sizer.Add(self.chk_ocp, 0, wx.ALIGN_CENTER)

        main_sizer.AddSpacer(15)

        # 4. 底部大开关
        self.btn_out = ModernButton(self, "OUTPUT OFF", size=(-1, 40), bg_color=THEME['btn_off'])
        self.btn_out.SetFont(wx.Font(11, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_out.Bind(wx.EVT_BUTTON, self.on_toggle_out)
        main_sizer.Add(self.btn_out, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(main_sizer)

    # --- 关键逻辑：连接检查 ---
    def check_conn(self):
        """
        拦截器：如果未连接，弹出提示并返回 False
        """
        if not self.driver.connected:
            dlg = wx.MessageDialog(self,
                                   f"仪器未连接！\nInstrument not connected.\n\n请先在上方选择资源并点击 Connect。",
                                   "操作被拒绝 / Access Denied", wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return False
        return True

    # --- 事件处理 (均包含 check_conn) ---
    def on_set_v(self, evt):
        if self.check_conn():
            try:
                self.driver.set_voltage(self.channel_id, float(self.txt_v.GetValue()))
            except:
                pass

    def on_set_i(self, evt):
        if self.check_conn():
            try:
                self.driver.set_current(self.channel_id, float(self.txt_i.GetValue()))
            except:
                pass

    def on_set_ovp(self, evt):
        if self.check_conn():
            try:
                self.driver.set_ovp(self.channel_id, float(self.txt_ovp.GetValue()))
            except:
                pass

    def on_set_ocp(self, evt):
        if self.check_conn():
            try:
                self.driver.set_ocp(self.channel_id, float(self.txt_ocp.GetValue()))
            except:
                pass

    def on_chk_ocp(self, evt):
        if self.check_conn():
            self.driver.set_ocp_state(self.channel_id, self.chk_ocp.GetValue())
        else:
            # 如果未连接，把勾选状态还原回去，避免UI误导
            self.chk_ocp.SetValue(not self.chk_ocp.GetValue())

    def on_toggle_out(self, evt):
        if self.check_conn():
            self.is_on = not self.is_on
            self.driver.set_output(self.channel_id, self.is_on)
            self.update_btn_ui()

    def update_btn_ui(self):
        if self.is_on:
            self.btn_out.SetLabel("OUTPUT ON")
            self.btn_out.SetBackgroundColour(THEME['btn_on'])
        else:
            self.btn_out.SetLabel("OUTPUT OFF")
            self.btn_out.SetBackgroundColour(THEME['btn_off'])
        self.btn_out.Refresh()

    def update_meas(self):
        if self.driver.connected:
            v, i, mode = self.driver.get_status(self.channel_id)
            self.read_v.SetLabel(f"{v:.3f}")
            self.read_i.SetLabel(f"{i:.3f}")
            self.lbl_mode.SetLabel(f"MODE: {mode}")

            if mode == "CC":
                self.lbl_mode.SetForegroundColour(wx.RED)
            elif mode == "CV":
                self.lbl_mode.SetForegroundColour(wx.GREEN)
            else:
                self.lbl_mode.SetForegroundColour(wx.WHITE)
            self.lbl_mode.Refresh()


# ===============================================================================
# 主窗口
# ===============================================================================
class ModernFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Siglent SPD4323X Command Center", size=(1100, 650))
        self.SetBackgroundColour(THEME['bg_main'])
        self.driver = SPD4323X_Driver()

        # 顶部工具栏面板
        top_panel = wx.Panel(self)
        top_panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        lbl_res = wx.StaticText(top_panel, label="VISA Address:")
        lbl_res.SetForegroundColour(wx.WHITE)
        top_sizer.Add(lbl_res, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)

        self.combo_res = wx.ComboBox(top_panel, size=(400, 30))
        top_sizer.Add(self.combo_res, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        btn_refresh = ModernButton(top_panel, "Scan", size=(80, 30), bg_color=wx.Colour(100, 100, 100))
        btn_refresh.Bind(wx.EVT_BUTTON, self.on_refresh)
        top_sizer.Add(btn_refresh, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        self.btn_conn = ModernButton(top_panel, "CONNECT", size=(100, 30), bg_color=THEME['btn_on'])
        self.btn_conn.Bind(wx.EVT_BUTTON, self.on_connect)
        top_sizer.Add(self.btn_conn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

        self.lbl_status = wx.StaticText(top_panel, label="Disconnected")
        self.lbl_status.SetForegroundColour(wx.Colour(255, 100, 100))
        top_sizer.Add(self.lbl_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)

        top_panel.SetSizer(top_sizer)

        # 主区域（通道）
        self.channel_panels = []
        grid_sizer = wx.GridSizer(1, 4, 15, 15)

        for i in range(1, 5):
            cp = ChannelPanel(self, i, self.driver)
            self.channel_panels.append(cp)
            grid_sizer.Add(cp, 1, wx.EXPAND)

        # 总体布局
        main_v_sizer = wx.BoxSizer(wx.VERTICAL)
        main_v_sizer.Add(top_panel, 0, wx.EXPAND | wx.ALL, 0)
        main_v_sizer.Add(grid_sizer, 1, wx.EXPAND | wx.ALL, 15)

        self.SetSizer(main_v_sizer)

        # 定时器
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.on_refresh(None)

    def on_refresh(self, evt):
        res = self.driver.list_resources()
        self.combo_res.SetItems(res)
        if res: self.combo_res.SetSelection(0)

    def on_connect(self, evt):
        if not self.driver.connected:
            addr = self.combo_res.GetValue()
            if not addr: return
            ok, msg = self.driver.connect(addr)
            if ok:
                self.lbl_status.SetLabel(f"LINKED: {msg}")
                self.lbl_status.SetForegroundColour(wx.GREEN)
                self.btn_conn.SetLabel("DISCONNECT")
                self.btn_conn.SetBackgroundColour(wx.Colour(200, 50, 50))
                self.timer.Start(1000)
            else:
                wx.MessageBox(f"连接失败:\n{msg}", "Error", wx.ICON_ERROR)
        else:
            self.timer.Stop()
            self.driver.close()
            self.lbl_status.SetLabel("Disconnected")
            self.lbl_status.SetForegroundColour(wx.Colour(255, 100, 100))
            self.btn_conn.SetLabel("CONNECT")
            self.btn_conn.SetBackgroundColour(THEME['btn_on'])

    def on_timer(self, evt):
        if self.driver.connected:
            for cp in self.channel_panels:
                cp.update_meas()

    def on_close(self, evt):
        self.timer.Stop()
        self.driver.close()
        evt.Skip()


if __name__ == '__main__':
    app = wx.App()
    frame = ModernFrame()
    frame.Show()
    app.MainLoop()
