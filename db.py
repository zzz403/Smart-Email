import sqlite3

def create_database():
    conn = sqlite3.connect('email_database.db')
    
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Emails (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            MessageID TEXT,
            FromEmail TEXT,
            ToEmail TEXT,
            Date TEXT,
            Subject TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Email_Content (
            Email_ID INTEGER,
            Body TEXT,
            FOREIGN KEY (Email_ID) REFERENCES Emails (ID)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AI_Summary (
            Email_ID INTEGER,
            Summary TEXT,
            FOREIGN KEY (Email_ID) REFERENCES Emails (ID)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AI_Categories (
            Email_ID INTEGER,
            Category TEXT,
            FOREIGN KEY (Email_ID) REFERENCES Emails (ID)
        )
    ''')

    conn.commit()

    conn.close()

    print("Database created and tables added!")

if __name__ == '__main__':
    create_database()
