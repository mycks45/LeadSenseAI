import sqlite3
import os

DB_NAME = "leads.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Create the leads table. We enforce a UNIQUE constraint on Name + Website
    # so we don't accidentally insert duplicate data when scraping the same area twice.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            website TEXT,
            instagram TEXT,
            facebook TEXT,
            linkedin TEXT,
            location TEXT,
            UNIQUE(name, website)
        )
    ''')
    conn.commit()
    conn.close()

def save_leads(leads):
    if not leads:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for lead in leads:
        cursor.execute('''
            INSERT INTO leads (name, phone, email, website, instagram, facebook, linkedin, location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, website) DO UPDATE SET
                phone=excluded.phone,
                email=excluded.email,
                instagram=excluded.instagram,
                facebook=excluded.facebook,
                linkedin=excluded.linkedin,
                location=excluded.location
        ''', (
            lead.get('Name', ''),
            lead.get('Phone', ''),
            lead.get('Email', ''),
            lead.get('Website', ''),
            lead.get('Instagram', ''),
            lead.get('Facebook', ''),
            lead.get('LinkedIn', ''),
            lead.get('Location', '')
        ))
        
    conn.commit()
    conn.close()

def get_all_leads():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Initialize the config
init_db()
