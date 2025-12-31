
import sqlite3
import os

def get_db_path():
    """Constructs the path to the database file in the project root."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(project_root, 'test_history.db')

def create_step_results_table():
    """
    Connects to the SQLite database and creates the 'test_step_results' table
    if it doesn't already exist. This table will store detailed numerical
    results for individual test steps, which is necessary for CPK analysis.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Database file not found at: {db_path}. Please run a test first to create it.")
        return

    try:
        con = sqlite3.connect(db_path)
        cursor = con.cursor()

        # SQL statement to create the new table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS test_step_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            measurement_value REAL NOT NULL,
            upper_limit REAL,
            lower_limit REAL,
            FOREIGN KEY (result_id) REFERENCES test_results (id)
        );
        """

        cursor.execute(create_table_sql)
        
        # Create an index for faster queries
        create_index_sql = "CREATE INDEX IF NOT EXISTS idx_result_id ON test_step_results (result_id);"
        cursor.execute(create_index_sql)

        con.commit()
        print("Successfully created or verified 'test_step_results' table and its index.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if con:
            con.close()

if __name__ == '__main__':
    print("Running database migration script...")
    create_step_results_table()
    print("Script finished.")
