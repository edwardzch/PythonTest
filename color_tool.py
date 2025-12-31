import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


class ColorPickerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")

        self.title("简易调色工具")
        self.geometry("350x420")
        self.resizable(False, False)

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        ttk.Label(main_frame, text="输入Hex颜色代码:", font=("Helvetica", 12)).pack(fill=X, pady=(0, 5))

        self.hex_var = tk.StringVar()
        self.hex_var.trace_add("write", self.update_color)
        self.hex_entry = ttk.Entry(main_frame, textvariable=self.hex_var, font=("Consolas", 14), justify='center')
        self.hex_entry.pack(fill=X, pady=5)

        # <<< --- 【【【核心修复1：使用标准的 tk.Frame】】】 --- >>>
        # 使用 tk.Frame 而不是 ttk.Frame，因为它直接支持 background 选项
        self.color_preview = tk.Frame(main_frame, height=150, relief="solid", borderwidth=1)
        self.color_preview.pack(fill=X, expand=YES, pady=15)

        self.hex_label = ttk.Label(main_frame, text="Hex: #", font=("Consolas", 12))
        self.hex_label.pack(fill=X, pady=2)

        self.rgb_label = ttk.Label(main_frame, text="RGB: ( , , )", font=("Consolas", 12))
        self.rgb_label.pack(fill=X, pady=2)

        self.copy_button = ttk.Button(main_frame, text="复制RGB值", command=self.copy_rgb, bootstyle="outline-success")
        self.copy_button.pack(fill=X, pady=(20, 0))

        self.hex_entry.focus_set()
        self.hex_var.set("#343A40")

    def update_color(self, *args):
        hex_code = self.hex_var.get().strip()

        if not hex_code.startswith('#'):
            hex_code = '#' + hex_code

        if len(hex_code) == 7:
            try:
                # <<< --- 【【【核心修复2：直接使用 .config(background=...)】】】 --- >>>
                # tk.Frame 可以直接配置背景色，不再需要 bootstyle
                self.color_preview.config(background=hex_code)

                r = int(hex_code[1:3], 16)
                g = int(hex_code[3:5], 16)
                b = int(hex_code[5:7], 16)

                self.hex_label.config(text=f"Hex: {hex_code.upper()}")
                self.rgb_label.config(text=f"RGB: ({r}, {g}, {b})")

            except (ValueError, tk.TclError):  # 捕获两种可能的错误
                self.show_invalid_state()
        else:
            self.show_invalid_state()

    def show_invalid_state(self):
        # <<< --- 【【【核心修复3：获取主题颜色来设置默认背景】】】 --- >>>
        # 从ttkbootstrap的style对象中获取默认的背景色
        default_bg = self.style.colors.get('bg')
        self.color_preview.config(background=default_bg)
        self.hex_label.config(text="Hex: 无效代码")
        self.rgb_label.config(text="RGB: (---, ---, ---)")

    def copy_rgb(self):
        rgb_text = self.rgb_label.cget("text")
        if "无效" not in rgb_text:
            value_to_copy = rgb_text.split(': ')[1]

            self.clipboard_clear()
            self.clipboard_append(value_to_copy)

            original_text = self.copy_button.cget("text")
            self.copy_button.config(text="已复制!", bootstyle="success")
            self.after(1500, lambda: self.copy_button.config(text=original_text, bootstyle="outline-success"))


if __name__ == "__main__":
    app = ColorPickerApp()
    app.mainloop()

