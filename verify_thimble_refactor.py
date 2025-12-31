import os
import shutil
import json
import time
from thimble_manager import ThimbleManager
from report_generator import ReportGenerator

# Setup test environment
TEST_DATA_FILE = 'thimble_data.json'
if os.path.exists(TEST_DATA_FILE):
    shutil.copy(TEST_DATA_FILE, TEST_DATA_FILE + ".bak")

# Create dummy V1 data
v1_data = {
    "test_seq_a.json": {"count": 10, "time_seconds": 100.0, "count_limit": 50},
    "test_seq_b.json": {"count": 5, "time_seconds": 50.0}
}
with open(TEST_DATA_FILE, 'w') as f:
    json.dump(v1_data, f)

print("--- Testing Migration ---")
manager = ThimbleManager()
data = manager._load_data()
print("Migrated Data:", json.dumps(data, indent=2))

assert "Station_1" in data
assert data["Station_1"]["version"] == 2
assert "Fix_test_seq_a" in data["Station_1"]["fixtures"]
assert data["Station_1"]["fixtures"]["Fix_test_seq_a"]["count"] == 10
print("Migration: PASS")

print("--- Testing Increment ---")
# Simulate running test_seq_a on Station_1
manager.increment_usage("test_seq_a.json", 10.0, "Station_1")
data = manager._load_data()
new_count = data["Station_1"]["fixtures"]["Fix_test_seq_a"]["count"]
print(f"Count after increment: {new_count}")
assert new_count == 11
print("Increment: PASS")

print("--- Testing Mapping Update ---")
# Map test_seq_c to Fix_test_seq_a (Same fixture)
fixtures = manager.get_fixtures("Station_1")
mappings = manager.get_mappings("Station_1")
mappings["test_seq_c.json"] = "Fix_test_seq_a"
manager.update_fixtures_and_mappings("Station_1", fixtures, mappings)

manager.increment_usage("test_seq_c.json", 10.0, "Station_1")
data = manager._load_data()
final_count = data["Station_1"]["fixtures"]["Fix_test_seq_a"]["count"]
print(f"Count after shared increment: {final_count}")
assert final_count == 12
print("Shared Increment: PASS")

print("--- Testing Report Generation ---")
results = [{'status': 'PASS', 'station_id': 'Station_1', 'duration': 1.0}]
config = {'app_version': '1.0.0', 'thimble_usage_info': 'Test Usage Info'}
gen = ReportGenerator(results, config)
report_path = gen.generate_report()
print(f"Report generated at: {report_path}")

with open(report_path, 'r', encoding='utf-8') as f:
    content = f.read()
    if "Test Usage Info" in content and "1.0.0" in content:
        print("Report Content Verification: PASS")
    else:
        print("Report Content Verification: FAIL")

# Cleanup
if os.path.exists(TEST_DATA_FILE + ".bak"):
    shutil.move(TEST_DATA_FILE + ".bak", TEST_DATA_FILE)
else:
    os.remove(TEST_DATA_FILE)
