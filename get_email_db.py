import imaplib
import email
import yaml
import logging
import sqlite3
from datetime import datetime
import chardet
from email.header import decode_header

# Function to load credentials from a YAML file
def load_credentials(filepath):
    try:
        with open(filepath, 'r') as file:
            credentials = yaml.safe_load(file)
            user = credentials['user']
            password = credentials['password']
            return user, password
    except Exception as e:
        logging.error(f"Failed to load credentials: {e}")
        raise

# Connect to Gmail's IMAP server
def connect_to_gmail_imap(user, password):
    imap_url = 'imap.gmail.com'
    try:
        mail = imaplib.IMAP4_SSL(imap_url)
        mail.login(user, password)
        mail.select('inbox')  # Select the inbox folder
        return mail
    except Exception as e:
        logging.error(f"Connection failed: {e}")
        raise

# Fetch emails for a specific recipient within a date range
def get_emails_by_recipient(mail, recipient_email, before_date, since_date):
    emails = []
    blocked_senders = ['Uber', 'Piazza']  # Blocked senders to skip processing
    try:
        print(f'AFTER "{since_date}" BEFORE "{before_date}" TO "{recipient_email}"')
        status, messages = mail.search(None, f'SINCE "{since_date}" BEFORE "{before_date}" TO "{recipient_email}"')
        print(messages)
        print(status)
        
        if status == 'OK':
            messages = messages[0].split()
            for mail_id in messages:
                # Fetch email content
                status, data = mail.fetch(mail_id, '(RFC822)')
                if status == 'OK':
                    msg = email.message_from_bytes(data[0][1])
                    msg_id = msg.get("Message-ID")

                    # Get sender details and skip blocked senders
                    from_ = msg.get("From")
                    if any(blocked.lower() in from_.lower() for blocked in blocked_senders):
                        print(f"Blocked sender: {from_}")
                        continue

                    # Decode email subject
                    raw_subject = msg["Subject"]
                    subject = decode_subject(raw_subject) if raw_subject else "No Subject"

                    # Extract other email details
                    to = msg.get("To")
                    date = parse_email_date(msg.get("Date"))
                    body = email_body_decode(msg)

                    # Add email details to the list
                    emails.append({
                        "message_id": msg_id,
                        "subject": subject,
                        "from": from_,
                        "to": to,
                        "date": date,
                        "body": body
                    })
        else:
            print("No messages found.")
    except Exception as e:
        logging.error(f"Failed to get emails by recipient: {e}")
        raise

    return emails

# Decode email subject with support for MIME encoding
def decode_subject(subject):
    try:
        decoded_fragments = decode_header(subject)
        subject_str = ""
        for fragment, encoding in decoded_fragments:
            if isinstance(fragment, bytes):
                encoding = encoding or 'utf-8'
                try:
                    subject_str += fragment.decode(encoding)
                except UnicodeDecodeError:
                    subject_str += fragment.decode('utf-8', errors='replace')
            else:
                subject_str += fragment
        return subject_str
    except Exception:
        return "cant read"

# Decode email body, supporting various encodings
def email_body_decode(msg):
    body = "this email can't read"
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Ensure we process only text and exclude attachments
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = decode_payload(payload)
                break
    else:
        # Handle non-multipart emails
        payload = msg.get_payload(decode=True)
        if payload:
            body = decode_payload(payload)

    return body

# Decode email payload with fallback for unknown encodings
def decode_payload(payload):
    try:
        return payload.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return payload.decode('iso-8859-1')
        except UnicodeDecodeError:
            try:
                return payload.decode('windows-1252')
            except UnicodeDecodeError:
                # Use chardet to detect encoding
                detected_encoding = chardet.detect(payload).get('encoding')
                if detected_encoding:
                    try:
                        return payload.decode(detected_encoding)
                    except UnicodeDecodeError:
                        pass
                return "this email can't read"

# Connect to the SQLite database
def connect_database(db_file='email_database.db'):
    conn = sqlite3.connect(db_file)
    return conn

# Adapters for datetime storage in SQLite
def adapt_datetime(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def convert_datetime(bytestring):
    return datetime.strptime(bytestring.decode("utf-8"), "%Y-%m-%d %H:%M:%S")

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("DATETIME", convert_datetime)

# Insert email details into the database
def insert_email(conn, email):
    try:
        cursor = conn.cursor()

        # Ensure date is a datetime object
        if isinstance(email['date'], str):
            email['date'] = datetime.strptime(email['date'], "%a, %d %b %Y %H:%M:%S %z")

        # Insert email metadata
        cursor.execute('''
            INSERT INTO Emails (FromEmail, ToEmail, Date, Subject, MessageID)
            VALUES (?, ?, ?, ?, ?)
        ''', (email['from'], email['to'], email['date'], email['subject'], email['message_id']))
        email_id = cursor.lastrowid

        # Insert email body
        cursor.execute('''
            INSERT INTO Email_Content (Email_ID, Body)
            VALUES (?, ?)
        ''', (email_id, email['body']))

        conn.commit()
        return email_id

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        return None

    finally:
        cursor.close()

# Check if an email exists in the database based on its Message ID
def email_exists(conn, message_id):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Emails WHERE MessageID = ?', (message_id,))
    return cursor.fetchone() is not None

# Save emails to the database
def save_emails_to_database(emails, conn):
    for email in emails:
        if email_exists(conn, email['message_id']):
            continue
        insert_email(conn, email)
    conn.close()
    print("Emails saved to database")

# Get the latest email date for a specific recipient
def get_latest_email_date(conn, email_account):
    cursor = conn.cursor()
    cursor.execute('SELECT MAX(Date) FROM Emails WHERE ToEmail = ?', (email_account,))
    row = cursor.fetchone()
    if row[0]:
        return pase_email_date_from_db(row[0])
    return None

# Parse email date strings to datetime objects
def parse_email_date(date_str):
    try:
        date_str = date_str.replace(" GMT", " +0000")
        if ',' in date_str:
            cleaned_date_str = date_str.split(" (")[0]
            return datetime.strptime(cleaned_date_str, "%a, %d %b %Y %H:%M:%S %z")
        else:
            cleaned_date_str = date_str.split(" (")[0]
            return datetime.strptime(cleaned_date_str, "%d %b %Y %H:%M:%S %z")
    except ValueError as e:
        print(f"Failed to parse date: {date_str}")
        raise e

# Format date strings from the database to the desired format
def pase_email_date_from_db(date_str):
    datetime_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    formatted_date_str = datetime_obj.strftime("%d-%b-%Y").upper()
    return formatted_date_str

# Main function to orchestrate the process
def main():
    # Load credentials and connect to the email server
    credentials = load_credentials('credentials.yaml')
    mail = connect_to_gmail_imap(*credentials)

    # Connect to the SQLite database
    conn = connect_database('email_database.db')
    recipient_email = 'zhengzhongze4@gmail.com'
    
    # Define date range
    before_date = '15-NOV-2024'
    since_date = get_latest_email_date(conn, recipient_email)
    if not since_date:
        since_date = '01-SEP-2024'

    # Fetch emails and save to the database
    emails = get_emails_by_recipient(mail, recipient_email, before_date, since_date)
    save_emails_to_database(emails, conn)

    # Logout from the email server
    mail.logout()

if __name__ == "__main__":
    main()
