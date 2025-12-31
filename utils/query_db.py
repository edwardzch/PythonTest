# utils/query_db.py
import sqlite3
from datetime import datetime, timedelta
import os
import sys
import pandas as pd
import numpy as np
from .app_utils import get_app_base_path

def get_db_path():
    """
    可靠地获取数据库文件的路径。
    数据库文件应与EXE或主启动脚本在同一目录下。
    """
    base_path = get_app_base_path()
    
    # 从配置文件读取数据库名称
    import json
    config_path = os.path.join(base_path, 'config.json')
    database_name = 'test_history'  # 默认值
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                database_name = config.get('database_name', 'test_history')
    except Exception as e:
        print(f"[QueryDB] 读取数据库配置失败，使用默认名称: {e}")
    
    return os.path.join(base_path, f'{database_name}.db')

def query_stats(start_date, end_date, stations=None, sequence_name=None, employee_id=None):
    """
    Queries the test_history.db for statistics within a given date range and filters.

    :param start_date: Start date string in 'YYYY-MM-DD' format.
    :param end_date: End date string in 'YYYY-MM-DD' format.
    :param stations: A list of station_id strings to include. If None, all stations are included.
    :param sequence_name: A specific sequence name to filter by. If None, all sequences are included.
    :return: A dictionary containing aggregated statistics.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"error": "Database file not found."}

    try:
        # The end_date from a date picker is the start of that day. To include the whole day, add one day to it.
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        end_date_iso = end_date_dt.isoformat()
        start_date_iso = datetime.strptime(start_date, '%Y-%m-%d').isoformat()

        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) # Read-only connection

        # Base query
        query = "SELECT * FROM test_results WHERE timestamp >= ? AND timestamp < ?"
        params = [start_date_iso, end_date_iso]

        # Add station filter
        if stations:
            placeholders = ','.join('?' for _ in stations)
            query += f" AND station_id IN ({placeholders})"
            params.extend(stations)

        # Add sequence name filter
        if sequence_name:
            query += " AND sequence_name = ?"
            params.append(sequence_name)

        # Add employee ID filter
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)

        df = pd.read_sql_query(query, con, params=params)
        con.close()

        if df.empty:
            return {
                "summary": {"total": 0, "pass": 0, "fail": 0, "pass_rate": 0, "avg_duration": 0},
                "fail_by_step": {},
                "fail_by_station": {},
                "pass_rate_over_time": {}
            }

        # Perform aggregations using pandas
        total = len(df)
        pass_count = len(df[df['status'] == 'PASS'])
        fail_count = total - pass_count
        pass_rate = (pass_count / total * 100) if total > 0 else 0
        avg_duration = df['duration'].mean()

        summary = {
            "total": int(total),
            "pass": int(pass_count),
            "fail": int(fail_count),
            "pass_rate": round(pass_rate, 2),
            "avg_duration": round(avg_duration, 2)
        }

        fail_df = df[df['status'] == 'FAIL']
        fail_by_step = fail_df['fail_step'].value_counts().to_dict()
        fail_by_station = fail_df['station_id'].value_counts().to_dict()

        # Pass rate over time (daily)
        # 2. Calculate daily stats from data
        df['date'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d')
        daily_stats_series = df.groupby('date')['status'].apply(lambda x: (x == 'PASS').sum() / len(x) * 100).round(2)
        pass_rate_over_time = daily_stats_series.to_dict()

        return {
            "summary": summary,
            "fail_by_step": fail_by_step,
            "fail_by_station": fail_by_station,
            "pass_rate_over_time": pass_rate_over_time
        }

    except Exception as e:
        print(f"[QueryDB] ERROR: Failed to query stats. Error: {e}")
        return {"error": str(e)}


def get_available_filters():
    """
    Queries the database to find all unique station IDs, sequence names, and employee IDs.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"stations": [], "sequences": [], "employee_ids": []}

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        stations = pd.read_sql_query("SELECT DISTINCT station_id FROM test_results WHERE station_id IS NOT NULL", con)[
            'station_id'].tolist()
        sequences = \
        pd.read_sql_query("SELECT DISTINCT sequence_name FROM test_results WHERE sequence_name IS NOT NULL", con)[
            'sequence_name'].tolist()

        # It's possible the employee_id column doesn't exist in older databases
        try:
            # =======================  唯一的优化点：增加 WHERE employee_id IS NOT NULL =======================
            # 这可以防止下拉框中出现一个由NULL值造成的空白选项
            query = "SELECT DISTINCT employee_id FROM test_results WHERE employee_id IS NOT NULL"
            employee_ids_df = pd.read_sql_query(query, con)

            # 检查返回的DataFrame是否为空，以及列名是否存在
            if not employee_ids_df.empty and 'employee_id' in employee_ids_df.columns:
                employee_ids = employee_ids_df['employee_id'].tolist()
            else:
                employee_ids = []

        except pd.io.sql.DatabaseError:
            employee_ids = []

        con.close()
        # 使用 set 去重并排序，确保结果干净
        return {
            "stations": sorted(list(set(stations))),
            "sequences": sorted(list(set(sequences))),
            "employee_ids": sorted(list(set(employee_ids)))
        }
    except Exception as e:
        print(f"[QueryDB] ERROR: Failed to get available filters. Error: {e}")
        return {"stations": [], "sequences": [], "employee_ids": []}


def query_cpk_stats(start_date, end_date, stations=None, sequence_name=None, employee_id=None):
    """
    Queries the database for detailed step results and calculates CPK for each step.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"error": "Database file not found."}

    try:
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        end_date_iso = end_date_dt.isoformat()
        start_date_iso = datetime.strptime(start_date, '%Y-%m-%d').isoformat()

        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

        # Base query joining the two tables
        query = """
        SELECT 
            s.step_name, s.measurement_value, s.upper_limit, s.lower_limit
        FROM test_step_results s
        JOIN test_results r ON s.result_id = r.id
        WHERE r.timestamp >= ? AND r.timestamp < ?
        AND s.upper_limit IS NOT NULL AND s.lower_limit IS NOT NULL
        """
        params = [start_date_iso, end_date_iso]

        # Add optional filters
        if stations:
            placeholders = ','.join('?' for _ in stations)
            query += f" AND r.station_id IN ({placeholders})"
            params.extend(stations)
        if sequence_name:
            query += " AND r.sequence_name = ?"
            params.append(sequence_name)
        if employee_id:
            # This might fail if the column doesn't exist. Add a try-except block.
            try:
                # Check if employee_id column exists before adding to query
                cursor = con.cursor()
                cursor.execute("PRAGMA table_info(test_results);")
                columns = [info[1] for info in cursor.fetchall()]
                if 'employee_id' in columns:
                    query += " AND r.employee_id = ?"
                    params.append(employee_id)
            except sqlite3.Error as e:
                 print(f"[QueryDB] WARNING: Could not check for employee_id column: {e}")


        df = pd.read_sql_query(query, con, params=params)
        con.close()

        if df.empty:
            return {}

        cpk_results = {}
        # Group by step name and perform analysis
        for step_name, group in df.groupby('step_name'):
            data = group['measurement_value'].to_numpy()

            # Use the first row's limits, assuming they are constant for the step
            usl = group['upper_limit'].iloc[0]
            lsl = group['lower_limit'].iloc[0]

            if len(data) < 2:  # Need at least 2 data points for std dev
                continue

            # CPK Calculation
            mean = np.mean(data)
            std_dev = np.std(data, ddof=1) # Sample standard deviation

            if std_dev == 0:
                cpk = "Infinity"
                cpu = "Infinity"
                cpl = "Infinity"
            else:
                try:
                    cpu = (usl - mean) / (3 * std_dev) if usl is not None else "Infinity"
                except ZeroDivisionError:
                    cpu = "Infinity"
                    
                try:
                    cpl = (mean - lsl) / (3 * std_dev) if lsl is not None else "Infinity"
                except ZeroDivisionError:
                    cpl = "Infinity"
                    
                if isinstance(cpu, str) or isinstance(cpl, str):
                     # If either is Infinity, take the numeric one, or Infinity if both are
                     numerics = [x for x in [cpu, cpl] if isinstance(x, (int, float))]
                     cpk = min(numerics) if numerics else "Infinity"
                else:
                     cpk = min(cpu, cpl)

            # Histogram data
            count, bins = np.histogram(data, bins='auto') # 'auto' is a good starting point

            # Sanitize values for JSON (NaN -> None)
            if pd.isna(usl): usl = None
            if pd.isna(lsl): lsl = None
            
            mean_val = round(mean, 4) if not pd.isna(mean) else None
            std_dev_val = round(std_dev, 4) if not pd.isna(std_dev) else None

            cpk_results[step_name] = {
                "cpk": round(cpk, 3) if isinstance(cpk, (int, float)) and not pd.isna(cpk) else cpk,
                "mean": mean_val,
                "std_dev": std_dev_val,
                "usl": usl,
                "lsl": lsl,
                "n": len(data),
                "histogram": {
                    "bins": [round(b, 6) for b in bins.tolist()],
                    "counts": count.tolist()
                }
            }

        return cpk_results

    except Exception as e:
        print(f"[QueryDB] ERROR: Failed to query CPK stats. Error: {e}")
        return {"error": str(e)}


def query_all_results_for_export(start_date, end_date, stations=None, sequence_name=None, employee_id=None):
    """
    Queries the test_history.db for all raw data within a given date range and filters,
    and returns headers and rows suitable for CSV export.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError("Database file not found.")

    try:
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        end_date_iso = end_date_dt.isoformat()
        start_date_iso = datetime.strptime(start_date, '%Y-%m-%d').isoformat()

        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = con.cursor()

        # Base query
        query = "SELECT * FROM test_results WHERE timestamp >= ? AND timestamp < ?"
        params = [start_date_iso, end_date_iso]

        # Add optional filters
        if stations:
            placeholders = ','.join('?' for _ in stations)
            query += f" AND station_id IN ({placeholders})"
            params.extend(stations)
        if sequence_name:
            query += " AND sequence_name = ?"
            params.append(sequence_name)
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)

        cursor.execute(query, params)

        # Fetch headers from cursor description
        headers = [description[0] for description in cursor.description]
        
        # Fetch all rows
        rows = cursor.fetchall()

        con.close()

        return headers, rows

    except Exception as e:
        print(f"[QueryDB] ERROR: Failed to export query results. Error: {e}")
        # Re-raise the exception so the Flask route can handle it
        raise e


if __name__ == '__main__':
    # Example usage for testing
    today = datetime.now().strftime('%Y-%m-%d')
    one_month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print("--- Available Filters ---")
    print(get_available_filters())

    print("\n--- Stats for last 30 days ---")
    stats = query_stats(start_date=one_month_ago, end_date=today)
    import json
    print(json.dumps(stats, indent=2, ensure_ascii=False))
