# ============================================
# GMAIL IMAP CHECKER — Flask API
# Primary tab (آخر 10) + SPAM folder (آخر 10)
# ============================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import imaplib
import email

app = Flask(__name__)
CORS(app)

SECRET_KEY = "my_secret_key_123"


def extract_domain_from_headers(raw_bytes, domain_lower):
    try:
        msg = email.message_from_bytes(raw_bytes)
        for header in ["From", "Sender"]:
            value = msg.get(header, "")
            if value and domain_lower in value.lower():
                return True
    except Exception:
        pass
    return False


def check_primary(mail, domain_lower):
    try:
        mail.select("INBOX", readonly=True)
        st, data = mail.search(None, 'X-GM-LABELS "^smartlabel_personal"')
        if st != "OK" or not data[0]:
            return False
        ids = data[0].split()
        if not ids:
            return False
        last10 = ids[-10:] if len(ids) >= 10 else ids
        for msg_id in reversed(last10):
            try:
                st2, msg_data = mail.fetch(msg_id, "(BODY[HEADER.FIELDS (FROM SENDER)])")
                if st2 != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                if extract_domain_from_headers(raw, domain_lower):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def check_spam(mail, domain_lower):
    for folder in ["[Gmail]/Spam", "[Google Mail]/Spam", "SPAM", "Junk"]:
        try:
            st, data = mail.select(folder, readonly=True)
            if st != "OK":
                continue
            total = int(data[0])
            if total == 0:
                continue
            start = max(1, total - 9)
            seq   = str(start) + ":" + str(total)
            st2, msg_data = mail.fetch(seq, "(BODY[HEADER.FIELDS (FROM SENDER)])")
            if st2 != "OK" or not msg_data:
                continue
            for item in msg_data:
                if not isinstance(item, tuple):
                    continue
                try:
                    raw = item[1]
                    if isinstance(raw, str):
                        raw = raw.encode("utf-8")
                    if extract_domain_from_headers(raw, domain_lower):
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def check_imap(gmail_user, gmail_pass, domain):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_user, gmail_pass)
    except imaplib.IMAP4.error as e:
        return "ERROR", "Login failed: " + str(e)
    except Exception as e:
        return "ERROR", "Connection failed: " + str(e)

    domain_lower = domain.lower()

    # SPAM أولاً
    if check_spam(mail, domain_lower):
        try: mail.logout()
        except: pass
        return "SPAM", ""

    # Primary
    if check_primary(mail, domain_lower):
        try: mail.logout()
        except: pass
        return "INBOX", ""

    try: mail.logout()
    except: pass
    return "NOTFOUND", ""


@app.route("/check", methods=["GET"])
def check():
    if request.args.get("key", "") != SECRET_KEY:
        return jsonify({"result": "ERROR", "msg": "Unauthorized"}), 401

    domain     = request.args.get("domain",   "").strip()
    email_addr = request.args.get("email",    "").strip()
    password   = request.args.get("password", "").strip()

    if not domain:
        return jsonify({"result": "ERROR", "msg": "No domain"}), 400
    if not email_addr or not password:
        return jsonify({"result": "ERROR", "msg": "No email or password"}), 400

    result, msg = check_imap(email_addr, password, domain)
    return jsonify({"result": result, "email": email_addr, "msg": msg})


@app.route("/debug", methods=["GET"])
def debug():
    if request.args.get("key", "") != SECRET_KEY:
        return jsonify({"result": "ERROR", "msg": "Unauthorized"}), 401

    email_addr = request.args.get("email",    "").strip()
    password   = request.args.get("password", "").strip()

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_addr, password)

        # --- 10 INBOX (Primary) ---
        mail.select("INBOX", readonly=True)
        st, data = mail.search(None, 'X-GM-LABELS "^smartlabel_personal"')
        ids = data[0].split() if data[0] else []
        last10 = ids[-10:] if len(ids) >= 10 else ids
        inbox_headers = []
        for msg_id in reversed(last10):
            st2, msg_data = mail.fetch(msg_id, "(BODY[HEADER.FIELDS (FROM SENDER)])")
            if msg_data and msg_data[0]:
                raw = msg_data[0][1]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                inbox_headers.append(raw.strip())

        # --- 10 SPAM ---
        spam_headers = []
        for folder in ["[Gmail]/Spam", "[Google Mail]/Spam"]:
            try:
                st, data = mail.select(folder, readonly=True)
                if st != "OK":
                    continue
                total = int(data[0])
                if total == 0:
                    continue
                start = max(1, total - 9)
                seq   = str(start) + ":" + str(total)
                st2, msg_data = mail.fetch(seq, "(BODY[HEADER.FIELDS (FROM SENDER)])")
                for item in msg_data:
                    if isinstance(item, tuple):
                        raw = item[1]
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="ignore")
                        spam_headers.append(raw.strip())
                break
            except Exception:
                continue

        mail.logout()
        return jsonify({
            "10_inbox": inbox_headers,
            "10_spam":  spam_headers
        })

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run()
