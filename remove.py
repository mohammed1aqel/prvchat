import sqlite3
import os

# Path to the uploaded database file
db_path = r"C:\Users\Admin\chat_monitor_dashboard\chat_messages_with_excel.db"

# Connect to the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all table names in the database
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

# Prepare deletion of all data from each table
for table_name in tables:
    table = table_name[0]
    cursor.execute(f"DELETE FROM {table}")
    conn.commit()

# Close the connection
conn.close()

# Confirm completion
tables_cleared = [table[0] for table in tables]
tables_cleared
