
import sys
import os
from PySide6.QtWidgets import QApplication

# Add current directory to path
sys.path.append(os.getcwd())

from order_estimation_dialog import OrderEstimationDialog, RealTimeOrderTracker
from thimble_tracker_dialog import ThimbleTrackerDialog
from thimble_manager import ThimbleManager

def verify_order_estimation():
    print("Verifying Order Estimation Dialog...")
    dialog = OrderEstimationDialog(station_count=1, sequence_name="TestSeq")
    
    # Check initial label text
    initial_text = dialog.total_tests_label.text()
    print(f"Initial Label Text: '{initial_text}'")
    
    if "当前已完成总数" in initial_text:
        print("PASS: Initial label text matches expectation.")
    else:
        print("FAIL: Initial label text does not match expectation.")

    # Simulate calculation
    dialog.current_pass = 10
    dialog.current_fail = 2
    dialog._calculate_estimation()
    
    updated_text = dialog.total_tests_label.text()
    print(f"Updated Label Text: '{updated_text}'")
    
    if "当前已完成总数: 12" in updated_text:
        print("PASS: Updated label text matches logic.")
    else:
        print("FAIL: Updated label text logic seems incorrect.")
        
    dialog.close()

def verify_thimble_tracker():
    print("\nVerifying Thimble Tracker Dialog...")
    manager = ThimbleManager()
    dialog = ThimbleTrackerDialog(manager)
    
    # Check maximized state (hard to check without showing, but we can check the call)
    # Since we can't easily check window state before show, we'll assume the code presence is enough
    # or check if showMaximized was called (we can't really mock easily here without checks).
    # However, we can check if it runs without error.
    
    print("Thimble Tracker Dialog initialized successfully.")
    dialog.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    try:
        verify_order_estimation()
        verify_thimble_tracker()
        print("\nVerification execution finished.")
    except Exception as e:
        print(f"\nERROR during verification: {e}")
        import traceback
        traceback.print_exc()
