# stats_app.py
import sys
import os
from flask import Flask, render_template, request, jsonify, Response
import io
import csv
from datetime import datetime
from utils.query_db import query_stats, get_available_filters, query_cpk_stats, query_all_results_for_export
from utils.app_utils import resource_path # Import resource_path
import webbrowser
from threading import Timer
import logging

# Disable Flask's default logging to keep the console clean for the main app
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Check for template folder, otherwise Flask will not start
template_folder_path = resource_path('templates')
static_folder_path = resource_path('static')

if not os.path.exists(template_folder_path):
    print(f"[StatsApp] CRITICAL: 'templates' directory not found at {template_folder_path}. Please create it.")
    sys.exit(1)

app = Flask(__name__,
            template_folder=template_folder_path,
            static_folder=static_folder_path)

@app.route('/')
def index():
    """Renders the main statistics report page."""
    return render_template('stats_report.html')

@app.route('/api/filters', methods=['GET'])
def api_get_filters():
    """Provides a list of available stations and sequences for the frontend filters."""
    try:
        filters = get_available_filters()
        return jsonify(filters)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    """
    Provides aggregated statistics based on query parameters.
    Query params:
    - startDate (YYYY-MM-DD)
    - endDate (YYYY-MM-DD)
    - stations (comma-separated string of station IDs)
    - sequence (a single sequence name)
    """
    try:
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        stations_str = request.args.get('stations')
        sequence = request.args.get('sequence')

        employee_id = request.args.get('employeeId')

        if not start_date or not end_date:
            return jsonify({"error": "startDate and endDate parameters are required."}), 400

        stations = stations_str.split(',') if stations_str else None

        stats = query_stats(start_date, end_date, stations, sequence, employee_id)

        if "error" in stats:
            return jsonify(stats), 500

        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cpk_stats', methods=['GET'])
def api_get_cpk_stats():
    """
    Provides CPK statistics based on query parameters.
    Query params:
    - startDate (YYYY-MM-DD)
    - endDate (YYYY-MM-DD)
    - stations (comma-separated string of station IDs)
    - sequence (a single sequence name)
    - employeeId (a single employee ID)
    """
    try:
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        stations_str = request.args.get('stations')
        sequence = request.args.get('sequence')
        employee_id = request.args.get('employeeId')

        if not start_date or not end_date:
            return jsonify({"error": "startDate and endDate parameters are required."}), 400

        stations = stations_str.split(',') if stations_str else None

        cpk_stats = query_cpk_stats(start_date, end_date, stations, sequence, employee_id)

        if "error" in cpk_stats:
            return jsonify(cpk_stats), 500

        return jsonify(cpk_stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/export_stats_report', methods=['GET'])
def export_stats_report():
    """
    Exports detailed test results as a CSV file based on query parameters,
    with custom formatting (adds serial number, splits timestamp, removes id).
    """
    try:
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        stations_str = request.args.get('stations')
        sequence = request.args.get('sequence')
        employee_id = request.args.get('employeeId')

        if not start_date or not end_date:
            return "Error: startDate and endDate parameters are required.", 400

        stations = stations_str.split(',') if stations_str else None

        # 1. Fetch original data
        orig_headers, orig_data = query_all_results_for_export(start_date, end_date, stations, sequence, employee_id)

        # 2. Process data for new format
        translation_map = {
            'sequence_name': '测试序列',
            'station_id': '工位号',
            'employee_id': '员工工号',
            'uut_sn': '产品序列号',
            'status': '测试结果',
            'duration': '测试耗时(秒)',
            'fail_step': '失败步骤',
            'fail_message': '失败信息'
        }
        new_headers = ['序号', '年', '月', '日', '时间']
        
        id_col_index = -1
        ts_col_index = -1
        
        # Preserve the order of original headers while creating the new translated header list
        ordered_orig_headers_to_process = []
        for i, header in enumerate(orig_headers):
            if header == 'id':
                id_col_index = i
                continue
            if header == 'timestamp':
                ts_col_index = i
                continue
            ordered_orig_headers_to_process.append(header)
        
        for header in ordered_orig_headers_to_process:
            new_headers.append(translation_map.get(header, header))

        new_rows = []
        for i, row in enumerate(orig_data):
            new_row = [i + 1] # Add serial number
            
            # Parse timestamp and add date/time parts
            ts_str = row[ts_col_index]
            # Handle potential timezone info (e.g., Z or +00:00) by stripping it
            if 'Z' in ts_str:
                ts_str = ts_str.replace('Z', '')
            if '+' in ts_str:
                ts_str = ts_str.split('+')[0]
            dt_obj = datetime.fromisoformat(ts_str)

            new_row.extend([dt_obj.year, dt_obj.month, dt_obj.day, dt_obj.strftime('%H:%M:%S')])

            # Add other columns, skipping id and timestamp
            processed_row_cells = []
            for j, cell in enumerate(row):
                if j not in [id_col_index, ts_col_index]:
                    processed_row_cells.append(cell)
            new_row.extend(processed_row_cells)
            
            new_rows.append(new_row)

        # 3. In-memory CSV file creation
        output = io.StringIO()
        output.write('\ufeff')  # BOM for Excel
        writer = csv.writer(output)
        
        writer.writerow(new_headers)
        writer.writerows(new_rows)
        
        csv_data = output.getvalue()
        
        # Use a dynamic filename with timestamp
        filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )

    except Exception as e:
        print(f"Error during CSV export: {e}")
        return f"An error occurred during export: {e}", 500

def open_browser():
    """Opens the web browser to the app's URL."""
    webbrowser.open_new("http://127.0.0.1:5678")

def run_app():
    """
    Runs the Flask application.
    This function is intended to be called from the main GUI application.
    """
    print("[StatsApp] Starting statistics server at http://127.0.0.1:5678")
    print("[StatsApp] Press Ctrl+C in the console running this script to stop the server.")
    # Browser opening is now handled by the main application
    # Timer(1, open_browser).start()  # Commented out to prevent duplicate browser windows
    # Note: Setting debug=False is important for running in a thread from the main app
    app.run(host='127.0.0.1', port=5678, debug=False)

if __name__ == '__main__':
    # This allows running the stats app directly for development/testing
    run_app()
