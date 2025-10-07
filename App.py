# app.py - Minimal Review Requester MVP (complete)
# Run: pip install -r requirements.txt
# Then: export (or create .env) the SMTP and APP_SECRET variables, then: python app.py

import sqlite3
from flask import Flask, request, jsonify, redirect, url_for, render_template_string
from itsdangerous import URLSafeSerializer, BadSignature
import smtplib
from email.message import EmailMessage
import os
from datetime import datetime
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

DB = 'reviews.db'
SECRET = os.getenv('APP_SECRET', 'replace-with-a-very-secret-string')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # e.g., no-reply@yourdomain.com
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.example.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')  # used for generated links

app = Flask(__name__)
s = URLSafeSerializer(SECRET, salt="review-sender")

# ---------------------------
# DB utilities
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            phone TEXT,
            name TEXT,
            order_id TEXT,
            created_at INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            provider TEXT, -- 'google' or 'trustpilot'
            provider_url TEXT, -- the direct review URL we redirect to
            token TEXT,
            sent_at INTEGER,
            clicked_at INTEGER,
            click_ip TEXT,
            metadata TEXT
        )
    ''')
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=False, many=False):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if many:
        c.executemany(query, params)
        conn.commit()
        conn.close()
        return
    c.execute(query, params)
    rv = c.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return rv

# ---------------------------
# Mail / helpers
# ---------------------------
def send_email(to_email, subject, body, html=None):
    if not SENDER_EMAIL or not SMTP_HOST:
        print("SMTP not configured; skipping send. Would send to:", to_email)
        return True
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    if html:
        msg.set_content(body)
        msg.add_alternative(html, subtype='html')
    else:
        msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if SMTP_USER and SMTP_PASS:
                smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False

def make_token(customer_id, provider, provider_url):
    payload = {"cid": customer_id, "provider": provider, "url": provider_url, "ts": int(datetime.utcnow().timestamp())}
    token = s.dumps(payload)
    return token

def parse_token(token):
    try:
        data = s.loads(token)
        return data
    except BadSignature:
        return None

# ---------------------------
# Routes / API
# ---------------------------

# Health
@app.route('/ping')
def ping():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})

# Add a customer (caller stores real customers who've purchased)
@app.route('/api/customers', methods=['POST'])
def api_add_customer():
    data = request.json or {}
    email = data.get('email')
    if not email:
        return jsonify({"error": "email required"}), 400
    name = data.get('name')
    phone = data.get('phone')
    order_id = data.get('order_id')
    now = int(datetime.utcnow().timestamp())
    db_execute('INSERT INTO customers (email,phone,name,order_id,created_at) VALUES (?,?,?,?,?)',
               (email, phone, name, order_id, now))
    cid = db_execute('SELECT last_insert_rowid()', fetch=True)[0][0]
    return jsonify({"id": cid, "email": email}), 201

# Send a review request for a customer to a provider (google/trustpilot)
# payload: { customer_id: int, provider: "google"|"trustpilot", provider_url: "https://..." }
@app.route('/api/send_request', methods=['POST'])
def api_send_request():
    data = request.json or {}
    cid = data.get('customer_id')
    provider = data.get('provider')
    provider_url = data.get('provider_url')
    if not cid or not provider or not provider_url:
        return jsonify({"error": "customer_id, provider and provider_url required"}), 400
    # minimal validation
    if provider not in ('google', 'trustpilot'):
        return jsonify({"error":"provider must be 'google' or 'trustpilot'"}), 400

    # create token and record
    token = make_token(cid, provider, provider_url)
    now = int(datetime.utcnow().timestamp())
    db_execute('INSERT INTO requests (customer_id,provider,provider_url,token,sent_at) VALUES (?,?,?,?,?)',
               (cid, provider, provider_url, token, now))
    # generate one-click link
    link = f"{BASE_URL}/r/{urllib.parse.quote(token)}"
    # build email
    # Keep emails simple and honest
    # The link goes to our redirector which logs the click then sends them to the real provider URL.
    # You may wish to build provider-specific landing pages to explain why they're being asked.
    customer = db_execute('SELECT email,name FROM customers WHERE id=?', (cid,), fetch=True)
    if not customer:
        return jsonify({"error":"customer not found"}), 404
    email = customer[0][0]
    name = customer[0][1] or ''
    subject = "Quick favor — leave a review?"
    body = f"Hi {name},\n\nThanks for your recent purchase. We’d really appreciate a short review — it helps small businesses like ours grow.\n\nPlease click the link below to leave a review:\n\n{link}\n\nThank you!\n"
    html = f"""
    <p>Hi {name},</p>
    <p>Thanks for your recent purchase. We’d really appreciate a short review — it helps small businesses like ours grow.</p>
    <p><a href="{link}">Click here to leave a review</a></p>
    <p>Thank you!</p>
    """
    sent = send_email(email, subject, body, html)
    return jsonify({"sent": bool(sent), "link": link}), 200

# Redirector that logs the click and sends the user to the provider review url
@app.route('/r/<token>')
def redirect_to_provider(token):
    token = urllib.parse.unquote(token)
    data = parse_token(token)
    if not data:
        return "Invalid or expired link.", 400
    # find request record
    rows = db_execute('SELECT id,customer_id FROM requests WHERE token=?', (token,), fetch=True)
    if not rows:
        return "Request not found.", 404
    req_id, customer_id = rows[0]
    # update click info
    now = int(datetime.utcnow().timestamp())
    click_ip = request.remote_addr
    db_execute('UPDATE requests SET clicked_at=?, click_ip=? WHERE id=?', (now, click_ip, req_id))
    # redirect to the actual provider URL (we stored it in token and provider_url column)
    provider_url = data.get('url')
    # best practice: ensure provider_url is absolute and safe; here we do a simple redirect
    return redirect(provider_url, code=302)

# Admin endpoint: list requests (simple)
@app.route('/admin/requests')
def admin_requests():
    rows = db_execute('''
        SELECT r.id, r.customer_id, c.email, r.provider, r.provider_url, r.sent_at, r.clicked_at, r.click_ip
        FROM requests r LEFT JOIN customers c ON r.customer_id=c.id
        ORDER BY r.sent_at DESC
        LIMIT 200
    ''', fetch=True)
    out = "<h2>Requests</h2><table border=1 cellpadding=6><tr><th>id</th><th>customer</th><th>provider</th><th>sent</th><th>clicked</th><th>ip</th><th>provider_url</th></tr>"
    for r in rows:
        sent = datetime.utcfromtimestamp(r[5]).isoformat() if r[5] else ''
        clicked = datetime.utcfromtimestamp(r[6]).isoformat() if r[6] else ''
        out += f"<tr><td>{r[0]}</td><td>{r[2]} (cid:{r[1]})</td><td>{r[3]}</td><td>{sent}</td><td>{clicked}</td><td>{r[7] or ''}</td><td><a href='{r[4]}' target='_blank'>link</a></td></tr>"
    out += "</table>"
    return out

# Basic landing page for readability if someone opens the redirect URL first
@app.route('/info')
def info_page():
    return render_template_string("""
    <h2>Review Requester</h2>
    <p>This service helps businesses send real customers one-click links to leave reviews on Google or Trustpilot.</p>
    """)

if __name__ == '__main__':
    print("Initializing DB...")
    init_db()
    print("Starting app on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
