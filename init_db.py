import sqlite3

connection = sqlite3.connect('database.db')

with connection:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            google_link TEXT,
            trustpilot_link TEXT
        );
    ''')

print("✅ Database initialized.")
