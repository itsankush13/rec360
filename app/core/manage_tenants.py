import sqlite3
import secrets
import sys
import hashlib
import argparse
from datetime import datetime, timedelta

from app.core.console import configure_utf8_output

# A cp1252 console must not fail on the rupee sign or box-drawing rule below.
for _stream in (sys.stdout, sys.stderr):
    configure_utf8_output(_stream)

DB_PATH = "tenants.db"

PLAN_LIMITS = {
    "trial":       {"resumes": 4,      "days": 2,    "price": 0,
                    "pdf_reports": 0,   "chatbot_answers": 0,
                    "pdf_free": False,  "chatbot_free": False},
    "six_months":  {"resumes": 200,    "days": 180,  "price": 16000,
                    "pdf_free": False,  "chatbot_free": False},
    "twelve_months":{"resumes": 999999,"days": 365,  "price": 25000,
                    "pdf_free": False,  "chatbot_free": False},
}

# Per-use pricing in rupees
PER_USE_PRICING = {
    "pdf_report":      75,   # ₹50 per PDF
    "chatbot_answer":  50,   # ₹15 per chatbot answer
}

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
            resumes_limit   INTEGER DEFAULT 10,
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

        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       TEXT,
            action          TEXT,
            detail          TEXT,
            timestamp       TEXT
        );
                       CREATE TABLE IF NOT EXISTS usage_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       TEXT NOT NULL,
            feature         TEXT NOT NULL,
            cost_rupees     INTEGER DEFAULT 0,
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wallet (
            tenant_id       TEXT PRIMARY KEY,
            balance_rupees  INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()

def log_action(tenant_id: str, action: str, detail: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO audit_log (tenant_id, action, detail, timestamp) VALUES (?,?,?,?)",
        (tenant_id, action, detail, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def add_tenant(company: str, hr_name: str, email: str,
               phone: str, plan: str = "trial") -> str:
    init_db()
    raw_key  = "tis_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    tenant_id = company.lower().replace(" ", "-")[:20] + "-" + secrets.token_hex(3)
    plan_info = PLAN_LIMITS[plan]
    expires   = (datetime.utcnow() + timedelta(days=plan_info["days"])).isoformat()
    is_paid   = 0 if plan == "trial" else 0  # always 0 until you confirm payment

    conn = get_db()
    conn.execute("""
        INSERT INTO tenants
        (id, company_name, hr_name, email, phone, api_key_hash,
         plan, is_active, is_paid, resumes_used, resumes_limit, created_at, expires_at)
        VALUES (?,?,?,?,?,?,?,1,?,0,?,?,?)
    """, (tenant_id, company, hr_name, email, phone, key_hash,
          plan, is_paid, plan_info["resumes"],
          datetime.utcnow().isoformat(), expires))
    conn.commit()
    conn.close()
    log_action(tenant_id, "CREATED", f"plan={plan}")

    print(f"\nTenant created!")
    print(f"   Company:   {company}")
    print(f"   HR Name:   {hr_name}")
    print(f"   Plan:      {plan} ({plan_info['resumes']} resumes, {plan_info['days']} days)")
    print(f"   Expires:   {expires[:10]}")
    print(f"\n   ── API KEY (send to company) ──")
    print(f"   {raw_key}")
    print(f"\n   ── DASHBOARD URL ──")
    print(f"   https://your-domain.com  OR  http://localhost:8501")
    print(f"   Login with: {phone} or {email}\n")
    return raw_key

def confirm_payment(email: str, plan: str, months: int = 1):
    init_db()
    plan_info = PLAN_LIMITS[plan]
    new_expiry = (datetime.utcnow() + timedelta(days=30 * months)).isoformat()
    conn = get_db()
    conn.execute("""
        UPDATE tenants
        SET plan=?, is_paid=1, is_active=1,
            resumes_used=0, resumes_limit=?, expires_at=?
        WHERE email=?
    """, (plan, plan_info["resumes"], new_expiry, email))
    conn.commit()
    conn.close()
    log_action(email, "PAYMENT_CONFIRMED", f"plan={plan}, months={months}")
    print(f"Payment confirmed for {email}")
    print(f"   Plan: {plan} | Resumes: {plan_info['resumes']} | Expires: {new_expiry[:10]}")

def block_tenant(email: str, reason: str = "Non-payment"):
    init_db()
    conn = get_db()
    conn.execute("UPDATE tenants SET is_active=0 WHERE email=?", (email,))
    conn.commit()
    conn.close()
    log_action(email, "BLOCKED", reason)
    print(f"Blocked: {email} - {reason}")

def unblock_tenant(email: str):
    init_db()
    conn = get_db()
    conn.execute("UPDATE tenants SET is_active=1 WHERE email=?", (email,))
    conn.commit()
    conn.close()
    log_action(email, "UNBLOCKED", "")
    print(f"Unblocked: {email}")

def list_tenants():
    init_db()
    conn = get_db()
    rows = conn.execute("""
        SELECT company_name, hr_name, phone, plan,
               resumes_used, resumes_limit, is_active,
               is_paid, expires_at
        FROM tenants ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    print(f"\n{'Company':<18} {'HR':<14} {'Phone':<13} {'Plan':<10} {'Used':<6} {'Limit':<7} {'Active':<8} {'Paid':<6} {'Expires'}")
    print("─" * 100)
    for r in rows:
        active = "Yes" if r["is_active"] else "No"
        paid   = "Yes" if r["is_paid"]   else "No"
        print(f"{r['company_name']:<18} {r['hr_name']:<14} {r['phone']:<13} "
              f"{r['plan']:<10} {r['resumes_used']:<6} {r['resumes_limit']:<7} "
              f"{active:<8} {paid:<6} {r['expires_at'][:10]}")

def check_expired():
    """Run this daily to auto-block expired tenants."""
    init_db()
    conn = get_db()
    now = datetime.utcnow().isoformat()
    expired = conn.execute("""
        SELECT id, company_name, email FROM tenants
        WHERE expires_at < ? AND is_active = 1
    """, (now,)).fetchall()
    for t in expired:
        conn.execute("UPDATE tenants SET is_active=0 WHERE id=?", (t["id"],))
        log_action(t["id"], "AUTO_BLOCKED", "Subscription expired")
        print(f"Auto-blocked: {t['company_name']} ({t['email']})")
    conn.commit()
    conn.close()
    if not expired:
        print("No expired tenants")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--add",             action="store_true")
    parser.add_argument("--list",            action="store_true")
    parser.add_argument("--block",           action="store_true")
    parser.add_argument("--unblock",         action="store_true")
    parser.add_argument("--confirm-payment", action="store_true")
    parser.add_argument("--check-expired",   action="store_true")
    parser.add_argument("--company",  type=str, default="")
    parser.add_argument("--hr-name",  type=str, default="")
    parser.add_argument("--email",    type=str, default="")
    parser.add_argument("--phone",    type=str, default="")
    parser.add_argument("--plan",     type=str, default="trial",
                        choices=["trial","starter","growth","enterprise"])
    parser.add_argument("--months",   type=int, default=1)
    parser.add_argument("--reason",   type=str, default="Non-payment")
    parser.add_argument("--add-credits",   action="store_true")
    parser.add_argument("--show-wallet",   action="store_true")
    parser.add_argument("--show-usage",    action="store_true")
    parser.add_argument("--amount",        type=int, default=0)
    args = parser.parse_args()

    if args.add:
        add_tenant(args.company, args.hr_name, args.email, args.phone, args.plan)
    elif args.list:
        list_tenants()
    elif args.block:
        block_tenant(args.email, args.reason)
    elif args.unblock:
        unblock_tenant(args.email)
    elif args.confirm_payment:
        confirm_payment(args.email, args.plan, args.months)
    elif args.check_expired:
        check_expired()
    elif args.add_credits:
        add_wallet_credits(args.email, args.amount)
    elif args.show_wallet:
        show_wallet(args.email)
    elif args.show_usage:
        show_usage(args.email)
    else:
        parser.print_help()

def add_wallet_credits(email: str, amount: int):
    """You call this after receiving manual payment."""
    conn = get_db()
    tenant = conn.execute(
        "SELECT id FROM tenants WHERE email=?", (email,)
    ).fetchone()
    if tenant:
        conn.execute("""
            INSERT INTO wallet (tenant_id, balance_rupees)
            VALUES (?, ?)
            ON CONFLICT(tenant_id)
            DO UPDATE SET balance_rupees = balance_rupees + ?
        """, (tenant["id"], amount, amount))
        conn.commit()
        print(f"Added ₹{amount} credits to {email}")
    conn.close()

def get_wallet_balance(tenant_id: str) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT balance_rupees FROM wallet WHERE tenant_id=?",
        (tenant_id,)
    ).fetchone()
    conn.close()
    return row["balance_rupees"] if row else 0

def charge_feature(tenant_id: str, feature: str) -> tuple[bool, str]:
    """
    Charge tenant for a feature. Returns (success, message).
    feature = 'pdf_report' or 'chatbot_answer'
    """
    cost = PER_USE_PRICING.get(feature, 0)
    if cost == 0:
        return True, ""

    balance = get_wallet_balance(tenant_id)
    if balance < cost:
        return False, f"Insufficient credits. Need ₹{cost}, have ₹{balance}. Contact TechXdigisolutions to top up."

    conn = get_db()
    conn.execute("""
        UPDATE wallet SET balance_rupees = balance_rupees - ?
        WHERE tenant_id = ?
    """, (cost, tenant_id))
    conn.execute("""
        INSERT INTO usage_log (tenant_id, feature, cost_rupees, timestamp)
        VALUES (?,?,?,?)
    """, (tenant_id, feature, cost, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    log_action(tenant_id, "CHARGED", f"{feature} ₹{cost}")
    return True, f"₹{cost} charged for {feature}"
def show_wallet(email: str):
    """Show wallet balance for a company."""
    conn = get_db()
    tenant = conn.execute(
        "SELECT id, company_name, plan FROM tenants WHERE email=?",
        (email,)
    ).fetchone()
    if not tenant:
        print(f"No tenant found for {email}")
        conn.close()
        return
    balance = get_wallet_balance(tenant["id"])
    print(f"\nWallet: {tenant['company_name']}")
    print(f"   Plan:    {tenant['plan']}")
    print(f"   Balance: ₹{balance}")
    conn.close()

def show_usage(email: str):
    """Show usage history for a company."""
    conn = get_db()
    tenant = conn.execute(
        "SELECT id, company_name FROM tenants WHERE email=?",
        (email,)
    ).fetchone()
    if not tenant:
        print(f"No tenant found for {email}")
        conn.close()
        return
    rows = conn.execute("""
        SELECT feature, cost_rupees, timestamp
        FROM usage_log WHERE tenant_id=?
        ORDER BY timestamp DESC LIMIT 20
    """, (tenant["id"],)).fetchall()
    conn.close()

    balance = get_wallet_balance(tenant["id"])
    total_spent = sum(r["cost_rupees"] for r in rows)

    print(f"\nUsage: {tenant['company_name']}")
    print(f"   Current Balance: ₹{balance}")
    print(f"   Total Spent:     ₹{total_spent}")
    print(f"\n   {'Feature':<20} {'Cost':<8} {'When'}")
    print("   " + "─" * 55)
    for r in rows:
        print(f"   {r['feature']:<20} ₹{r['cost_rupees']:<7} {r['timestamp'][:16]}")