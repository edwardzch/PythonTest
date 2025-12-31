
import sqlite3
import os

def get_db_path():
    project_root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(project_root, 'test_history.db')

def print_db_schema():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Database file not found at: {db_path}")
        return

    try:
        con = sqlite3.connect(db_path)
        cursor = con.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in the database:")
        for table_name in tables:
            table_name = table_name[0]
            print(f"  Table: {table_name}")
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            for col in columns:
                print(f"    Column: {col[1]} (Type: {col[2]}, NotNull: {col[3]}, PK: {col[5]})")
        con.close()
    except Exception as e:
        print(f"Error reading database schema: {e}")

if __name__ == '__main__':
    print_db_schema()
