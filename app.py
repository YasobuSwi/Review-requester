from flask import Flask, render_template, request, session, redirect, url_for, flash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import os
from werkzeug.security import check_password_hash, generate_password_hash

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
        user = conn.execute("SELECT * FROM businesses WHERE email = ? , (email,)).fetchone()
        conn.close()

    if user and check_password_hash(user['password_hash'], password):
        session['user_email'] = email
        flash('✅Logged in successfully.')
        return redirect(url_for('dashboard'))
    else:
        flash('❌Invalid login details')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('✅Logged out successfully.')
    return redirect(url_for('login'))


from flask import request, session, render_template
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

@app.route('/send_email', methods=['POST'])
def send_email():
    # 🔒 Make sure the user is logged in
    if 'user_email' not in session:
        return "❌ You must be logged in to send review requests.", 403

    # 📩 Get customer details from the form
    name = request.form['name']
    customer_email = request.form['email']

    # 🧑‍💼 Get the business's review links from the database
    business_email = session['user_email']
    conn = get_db_connection()
    row = conn.execute(
        "SELECT google_link, trustpilot_link FROM businesses WHERE email = ?",
        (business_email,)
    ).fetchone()
    conn.close()

    if not row:
        return "❌ No review links found for this business.", 404

    google_link = row['google_link']
    trustpilot_link = row['trustpilot_link']

    # 📨 Build the email content dynamically
    body_lines = [
        f"Hi {name},",
        "\nThank you for choosing us!",
        "\nCould you take a minute to leave us a review? It really helps small businesses like ours grow."
    ]

    if google_link:
        body_lines.append(f"\n🌟 Google Reviews: {google_link}")
    if trustpilot_link:
        body_lines.append(f"\n⭐ Trustpilot: {trustpilot_link}")

    body_lines.append("\nWe truly appreciate your support 🙏")
    body = "\n".join(body_lines)

    # ✉️ Setup the email
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = customer_email
    msg['Subject'] = "We’d love your feedback ⭐"
    msg.attach(MIMEText(body, 'plain'))

    # 🚀 Send the email using Gmail SMTP
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, customer_email, msg.as_string())
        return render_template('success.html')
    except Exception as e:
        print(f"Email send error: {e}")
        return f"❌ Failed to send email: {e}", 500


from flask import flash  # put this at the top too

from werkzeug.security import generate_password_hash

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        google_link = request.form.get('google_link', '').strip()
        trustpilot_link = request.form.get('trustpilot_link', '').strip()

        # Enforce that at least one link must be provided
        if not google_link and not trustpilot_link:
            return "❌ Please provide at least one review link (Google or Trustpilot).", 400

        # ✅ Hash the password before saving
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO businesses (email, password_hash, google_link, trustpilot_link)
                VALUES (?, ?, ?, ?)
            """, (email, hashed_password, google_link or None, trustpilot_link or None))
            conn.commit()
        except Exception as e:
            conn.close()
            return f"❌ Sign up failed: {e}", 400

        conn.close()
        session['user_email'] = email
        return redirect(url_for('dashboard'))

    return render_template('signup.html')


@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/update_links_page')
def update_links_page():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('update_links.html')

@app.route('/update_links', methods=['POST'])
def update_links():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    google_link = request.form.get('google_link')
    trustpilot_link = request.form.get('trustpilot_link')
    email = session['user_email']

    conn = get_db_connection()
    conn.execute("""
        UPDATE businesses
        SET google_link = ?, trustpilot_link = ?
        WHERE email = ?
    """, (google_link, trustpilot_link, email))
    conn.commit()
    conn.close()

    flash('✅ Your links have been updated!')
    return redirect(url_for('dashboard'))

@app.route('/send')
def send_review():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('send.html')

# ---------------------------
# Run app
# ---------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
