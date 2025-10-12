from flask import Flask, render_template, request, session, redirect, url_for
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import os

# ---------------------------
# Flask app setup
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')


# ---------------------------
# Database helper
# ---------------------------
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def home():
    # If logged in, show send page link
    if 'user_email' in session:
        return render_template('index.html', logged_in=True)
    else:
        return render_template('index.html', logged_in=False)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM businesses WHERE email = ? AND password_hash = ?", (email, password)).fetchone()
        conn.close()

        if user:
            session['user_email'] = email
            return redirect(url_for('send_review'))
        else:
            return "❌ Invalid login details", 401

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('home'))


@app.route('/send')
def send_review():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('send.html')


@app.route('/send_email', methods=['POST'])
def send_email():
    if 'user_email' not in session:
        return "❌ You must be logged in to send review requests.", 403

    # Get form data
    name = request.form['name']
    customer_email = request.form['email']

    # Get business's review links from DB
    business_email = session['user_email']
    conn = get_db_connection()
    row = conn.execute("SELECT google_link, trustpilot_link FROM businesses WHERE email = ?", (business_email,)).fetchone()
    conn.close()

    if not row:
        return "❌ No review links found for this business. Please set them up first.", 404

    google_link = row['google_link']
    trustpilot_link = row['trustpilot_link']

    # Email credentials (from Render env)
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')

    # Build the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = customer_email
    msg['Subject'] = "We'd love your feedback ⭐"

    body = f"""
    Hi {name},

    Thank you for choosing us!

    Could you take a minute to leave us a review? It really helps.

    🌟 Google Reviews: {google_link}
    ⭐ Trustpilot: {trustpilot_link}

    Thanks so much 🙏
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, customer_email, msg.as_string())
        return render_template('success.html')
    except Exception as e:
        print(f"Email send error: {e}")
        return f"❌ Failed to send email: {e}", 500


# ---------------------------
# Run app
# ---------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
