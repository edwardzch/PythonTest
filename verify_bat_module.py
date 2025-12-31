import sys
import os

# Add current directory to sys.path so we can import test_modules
sys.path.append(os.getcwd())

from test_modules.process_utils import run_bat_script

bat_path = os.path.abspath("test_bat.bat")
print(f"Testing execution of: {bat_path}")

success, message = run_bat_script(bat_path)

print(f"Success: {success}")
print(f"Message:\n{message}")

if success and "Hello from BAT file!" in message:
    print("VERIFICATION PASSED")
else:
    print("VERIFICATION FAILED")
