
import sys
import os

# Add current directory to path so we can import utils if needed, 
# though we just want to import the module to access HTML_TEMPLATE
sys.path.append(os.getcwd())

try:
    import work_order_history_report
    print("Successfully imported work_order_history_report")
    
    template = work_order_history_report.HTML_TEMPLATE
    
    # Try formatting with dummy data
    formatted = template.format(
        gen_time="2024-01-01 12:00:00",
        table_rows="<tr><td>Test</td></tr>"
    )
    
    print("Successfully formatted HTML_TEMPLATE")
    
    # Check if CSS braces are present in output (single braces)
    if "body { font-family" in formatted:
        print("CSS braces preserved correctly")
    else:
        print("CSS braces missing or corrupted")
        print(formatted[:500]) # Print first 500 chars to debug

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
