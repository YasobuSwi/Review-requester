import sqlite3

# Create or overwrite the database file
conn = sqlite3.connect('database.db')

with conn:
    # Drop the old table if it exists
    conn.execute('DROP TABLE IF EXISTS businesses')

    # Create the new table
    conn.execute('''
        CREATE TABLE businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            google_link TEXT,
            trustpilot_link TEXT
        )
    ''')

print("✅ Database initialized successfully.")
conn.close()
