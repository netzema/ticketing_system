from flask import Flask, render_template_string, render_template, g
import sqlite3
from datetime import datetime

DB = "tickets.db"
app = Flask(__name__)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
    return g.db

@app.route("/validate/<tid>")
def validate(tid):
    db = get_db()
    cur = db.execute("SELECT scanned_at FROM tickets WHERE ticket_id = ?", (tid,))
    row = cur.fetchone()
    if not row:
        msg = "❌ Invalid ticket"
        color = "red"
    elif row[0] is None:
        now = datetime.now()
        db.execute("UPDATE tickets SET scanned_at = ? WHERE ticket_id = ?", (now, tid))
        db.commit()
        msg = "✅ Ticket valid. Welcome!"
        color = "green"
    else:
        msg = "❌ Ticket already used"
        color = "red"
    html = """
    <html><head><title>Scan Result</title></head>
    <body style="text-align:center;font-family:sans-serif">
      <h1 style="color:{{color}}">{{msg}}</h1>
    </body></html>"""
    return render_template_string(html, msg=msg, color=color)

@app.route("/scan")
def scan():
    # Renders the scan.html template
    return render_template("scan.html")

if __name__ == "__main__":
    app.run(
      host="0.0.0.0",
      port=8000,
      ssl_context=('cert.pem','key.pem')
    )
