import sqlite3
import secrets
import hashlib
import random
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tenants.db"
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tenants (
            id              TEXT PRIMARY KEY,
            company_name    TEXT NOT NULL,
            hr_name         TEXT NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            phone           TEXT UNIQUE NOT NULL,
            api_key_hash    TEXT UNIQUE NOT NULL,
            plan            TEXT DEFAULT 'trial',
            is_active       INTEGER DEFAULT 1,
            is_paid         INTEGER DEFAULT 0,
            resumes_used    INTEGER DEFAULT 0,
            resumes_limit   INTEGER DEFAULT 4,
            created_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            notes           TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS otp_store (
            phone_or_email  TEXT PRIMARY KEY,
            otp_hash        TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            attempts        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_token   TEXT PRIMARY KEY,
            tenant_id       TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tenant_credentials (
            tenant_id     TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       TEXT,
            action          TEXT,
            detail          TEXT,
            timestamp       TEXT
        );
    """)
    conn.commit()
    conn.close()

def log_action(tenant_id: str, action: str, detail: str = ""):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO audit_log (tenant_id,action,detail,timestamp) VALUES(?,?,?,?)",
            (tenant_id, action, detail, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def _store_otp(identifier: str) -> str:
    otp      = str(random.randint(100000, 999999))
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires  = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    conn     = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO otp_store
        (phone_or_email, otp_hash, expires_at, attempts)
        VALUES (?,?,?,0)
    """, (identifier, otp_hash, expires))
    conn.commit()
    conn.close()
    return otp

def send_phone_otp(phone: str) -> bool:
    try:
        from twilio.rest import Client
        otp = _store_otp(phone)
        client = Client(os.getenv("TWILIO_ACCOUNT_SID"),
                        os.getenv("TWILIO_AUTH_TOKEN"))
        client.messages.create(
            body=f"Your TechXdigisolutions OTP: {otp}\nValid 10 minutes.",
            from_=os.getenv("TWILIO_PHONE"),
            to=phone
        )
        return True
    except Exception as e:
        otp = _store_otp(phone)
        print(f"\n🔑 OTP for {phone}: {otp}  (valid 10 min)\n")
        return True

def send_email_otp(email: str) -> tuple[bool, str]:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host     = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port     = int(os.getenv("SMTP_PORT", 465))
    sender_email  = os.getenv("SENDER_EMAIL", "")
    sender_pass   = os.getenv("SENDER_PASSWORD", "")

    # ✅ Fail fast if credentials aren't configured
    if not sender_email or not sender_pass:
        return False, "Email credentials not configured (SENDER_EMAIL / SENDER_PASSWORD missing)"

    otp = _store_otp(email)

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = "Your TechXdigisolutions Login OTP"
    msg["From"]    = sender_email
    msg["To"]      = email

    html = f"""
    <html><body style="font-family:Arial,sans-serif;padding:30px;background:#07090f;">
        <div style="max-width:480px;margin:auto;background:#111827;
                    border-radius:16px;padding:32px;border:1px solid #1e2d45;">
            <h2 style="color:#6366f1;text-align:center;">TechXdigisolutions</h2>
            <p style="color:#94a3b8;text-align:center;">Your login OTP is:</p>
            <div style="font-size:2.5rem;font-weight:900;color:#6366f1;
                        letter-spacing:12px;padding:24px;background:#0b0f1a;
                        border-radius:12px;text-align:center;
                        border:1px solid #1e2d45;">{otp}</div>
            <p style="color:#475569;text-align:center;margin-top:20px;font-size:0.85rem;">
                Valid for 10 minutes. Do not share this with anyone.
            </p>
        </div>
    </body></html>"""
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, sender_pass)
            server.sendmail(sender_email, email, msg.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — check SENDER_EMAIL and SENDER_PASSWORD (Gmail needs an App Password)"
    except smtplib.SMTPConnectError:
        return False, f"Could not connect to SMTP server {smtp_host}:{smtp_port}"
    except Exception as e:
        return False, f"Email send failed: {str(e)}"

def verify_otp(identifier: str, entered_otp: str) -> tuple[bool, str]:
    conn = get_db()
    row  = conn.execute("""
        SELECT otp_hash, expires_at, attempts
        FROM otp_store WHERE phone_or_email=?
    """, (identifier,)).fetchone()
    if not row:
        conn.close()
        return False, "No OTP found. Please request a new one."
    if row["attempts"] >= 5:
        conn.close()
        return False, "Too many attempts. Please request a new OTP."
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.close()
        return False, "OTP expired. Please request a new one."
    entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
    if entered_hash != row["otp_hash"]:
        conn.execute("""
            UPDATE otp_store SET attempts=attempts+1
            WHERE phone_or_email=?
        """, (identifier,))
        conn.commit()
        conn.close()
        remaining = 4 - row["attempts"]
        return False, f"Wrong OTP. {remaining} attempts remaining."
    conn.execute("DELETE FROM otp_store WHERE phone_or_email=?", (identifier,))
    conn.commit()
    conn.close()
    return True, ""

def create_session(tenant_id: str) -> str:
    token   = secrets.token_urlsafe(48)
    expires = (datetime.utcnow() + timedelta(hours=8)).isoformat()
    conn    = get_db()
    conn.execute("""
        INSERT INTO sessions (session_token,tenant_id,created_at,expires_at)
        VALUES (?,?,?,?)
    """, (token, tenant_id, datetime.utcnow().isoformat(), expires))
    conn.commit()
    conn.close()
    return token

def validate_session(token: str) -> dict | None:
    if not token:
        return None
    conn = get_db()
    row  = conn.execute("""
        SELECT s.tenant_id, s.expires_at,
               t.company_name, t.hr_name, t.plan,
               t.is_active, t.is_paid,
               t.resumes_used, t.resumes_limit,
               t.expires_at as sub_expires
        FROM sessions s
        JOIN tenants t ON s.tenant_id = t.id
        WHERE s.session_token=?
    """, (token,)).fetchone()
    conn.close()
    if not row:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None
    if not row["is_active"]:
        return None
    if datetime.fromisoformat(row["sub_expires"]) < datetime.utcnow():
        return None
    return dict(row)

def get_tenant_by_identifier(identifier: str) -> dict | None:
    init_db()
    conn = get_db()
    row  = conn.execute("""
        SELECT * FROM tenants
        WHERE phone=? OR email=?
    """, (identifier, identifier)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_default_login_tenant() -> dict | None:
    """Return the active admin tenant used by the single QChem login."""
    init_db()
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM tenants
        WHERE plan='admin' AND is_active=1
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()
    conn.close()
    return dict(row) if row else None


def set_tenant_password(tenant_id: str, username: str, plain_password: str) -> tuple[bool, str]:
    import bcrypt
    if len(plain_password) < 8:
        return False, "Password must be at least 8 characters."
    hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO tenant_credentials
            (tenant_id, username, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (tenant_id, username.strip().lower(), hashed, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return True, "Credentials set successfully."
    except Exception as e:
        return False, str(e)


def verify_password_login(username: str, plain_password: str) -> tuple[dict | None, str]:
    import bcrypt
    conn = get_db()
    row = conn.execute("""
        SELECT tc.tenant_id, tc.password_hash,
               t.company_name, t.hr_name, t.email, t.plan,
               t.is_active, t.is_paid, t.resumes_used,
               t.resumes_limit, t.expires_at
        FROM tenant_credentials tc
        JOIN tenants t ON tc.tenant_id = t.id
        WHERE tc.username = ?
    """, (username.strip().lower(),)).fetchone()
    conn.close()

    if not row:
        return None, "Invalid username or password."
    if not row["is_active"]:
        return None, "Account suspended. Contact TechXdigisolutions."
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None, "Subscription expired. Contact TechXdigisolutions."

    try:
        match = bcrypt.checkpw(plain_password.encode(), row["password_hash"].encode())
    except Exception:
        return None, "Authentication error."

    if not match:
        return None, "Invalid username or password."

    return dict(row), ""
