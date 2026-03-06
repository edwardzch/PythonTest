# drivers/real/fluke_8808a.py
# Based on the user-provided, debugged testfluke.py

import pyvisa
import time

class Fluke8808A:
    """Driver for Fluke 8808A Multimeter, using a two-step command protocol."""

    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "Fluke8808A",
        "display_name": "福禄克 8808A 万用表",
        "category": "multimeter",
        "interface": "visa",
    }
    
    # ========== 配置 Tab 定义（动态生成 Tab）==========
    CONFIG_TAB = {
        "tab_name": "Fluke8808A 配置",
        "config_key": "dmm_config",
        "mode": "shared",
    }
    
    # ========== 配置表单定义（支持共享/独立模式）==========
    CONFIG_SCHEMA = {
        "dmm_mode": {
            "type": "mode_switch",
            "label": "万用表模式",
            "shared_label": "共享模式（多工位共用一台万用表）",
            "independent_label": "独立模式（每工位独立万用表）",
            "shared_config_key": "shared_config",
            "station_count": 4,
            
            # 共享模式配置
            "shared_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "ASRL1::INSTR",
                    "auto_connect_default": True
                },
                "default_mode": {
                    "type": "select",
                    "label": "默认模式",
                    "options": ["DCV", "ACV", "DCI", "ACI", "RES", "DIODE", "FREQ", "CONT"],
                    "default": "DCV"
                }
            },
            
            # 独立模式配置
            "independent_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "",
                    "auto_connect_default": True
                },
                "default_mode": {
                    "type": "select",
                    "label": "默认模式",
                    "options": ["DCV", "ACV", "DCI", "ACI", "RES", "DIODE", "FREQ", "CONT"],
                    "default": "DCV"
                }
            }
        }
    }


    CONFIG_COMMANDS = {
        "DCV": "VDC",
        "ACV": "VAC",
        "DCI": "ADC",
        "ACI": "AAC",
        "RES": "OHMS",
        "DIODE": "DIOD",
        "FREQ": "HZ",
        "CONT": "CONT"
    }
    FETCH_COMMAND = "VAL1?"

    def _robust_query(self, query_string):
        """Sends a query and reads both the data and the subsequent prompt."""
        self.instrument.write(query_string)
        data = self.instrument.read().strip()
        prompt = self.instrument.read().strip()
        if prompt in ["?>", "!>"]:
            raise Exception(f"Query command '{query_string}' failed with prompt: {prompt}")
        return data

    def __init__(self, visa_address):
        self.visa_address = visa_address
        self.rm = pyvisa.ResourceManager()
        self.instrument = None
        print(f"Fluke 8808A driver initialized for {visa_address}")

    def connect(self):
        if self.is_connected():
            return
        try:
            self.instrument = self.rm.open_resource(
                self.visa_address,
                read_termination='\r\n',
                write_termination='\r',
                baud_rate=9600,
                timeout=5000
            )
            # Enter remote mode
            self._write_config_command("REMS")
            
            # Get IDN using the robust query
            idn = self._robust_query("*IDN?")
            print(f"✅ Successfully connected to Fluke 8808A: {idn}")

        except Exception as e:
            print(f"❌ Failed to connect to Fluke 8808A at {self.visa_address}. Error: {e}")
            self.instrument = None # Ensure instrument is None on failure
            raise # Re-raise the exception to be caught by HardwareManager

    def is_connected(self):
        """Checks if the instrument is currently connected."""
        # A simple check is to see if the instrument object exists.
        # A more robust check might involve a quick query.
        return self.instrument is not None

    def _write_config_command(self, command):
        """Writes a configuration command and clears the returned prompt."""
        self.instrument.write(command)
        prompt = self.instrument.read().strip()
        if prompt in ["?", "!>"]:
            raise Exception(f"Configuration command '{command}' failed with prompt: {prompt}")

    def _query_value(self):
        """Queries the instrument for its value using the robust query method."""
        data = self._robust_query(self.FETCH_COMMAND)
        try:
            value_str = data.split()[0]
            return float(value_str)
        except (ValueError, IndexError):
            print(f"Warning: Could not parse DMM value from response: '{data}'")
            return None

    def set_mode(self, mode_key):
        """Sets the measurement function of the multimeter."""
        config_cmd = self.CONFIG_COMMANDS.get(mode_key.upper())
        if not config_cmd:
            raise ValueError(f"Invalid measurement mode key: {mode_key}")
        self._write_config_command(config_cmd)
        # A short delay after setting the mode is good practice
        time.sleep(0.2)

    def read_value(self):
        """Reads the currently displayed value from the multimeter."""
        return self._query_value()

    def close(self):
        """Return instrument to local mode and close connection."""
        if self.instrument:
            try:
                self.instrument.write("LOCS")
            except Exception as e:
                print(f"Warning: Failed to return instrument to local mode: {e}")
            finally:
                self.instrument.close()
                self.instrument = None
                print("DMM connection closed.")