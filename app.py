from flask import Flask, render_template_string, render_template, g
import sqlite3
from datetime import datetime
from config import BASE_PATH, PORT

DB = f"{BASE_PATH}/tickets.db"
app = Flask(__name__)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
    return g.db

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/validate/<tid>")
def validate(tid):
    db = get_db()
    cur = db.execute("SELECT scanned_at FROM tickets WHERE ticket_id = ?", (tid,))
    row = cur.fetchone()

    count = None  # default: don’t show it
    if not row:
        msg = "❌ Ungültiges Ticket."
        color = "red"
    elif row[0] is None:
        now = datetime.now()
        db.execute("UPDATE tickets SET scanned_at = ? WHERE ticket_id = ?", (now, tid))
        db.commit()
        msg = "✅ Ticket gültig!"
        color = "green"

        # show how many tickets have been validated so far
        count = db.execute("SELECT COUNT(*) FROM tickets WHERE scanned_at IS NOT NULL").fetchone()[0]
    else:
        msg = "❌ Ticket bereits verwendet."
        color = "red"

    html = """
    <html>
      <head><title>Scan Result</title></head>
      <body style="text-align:center;font-family:sans-serif">
        <h1 style="color:{{ color }}">{{ msg }}</h1>
        {% if count is not none %}
        <p style="font-size:1.5em;">Bereits eingescannt: <strong>{{ count }}</strong></p>
        {% endif %}
      </body>
    </html>
    """
    return render_template_string(html, msg=msg, color=color, count=count)

@app.route("/scan")
def scan():
    # Renders the scan.html template
    return render_template("scan.html")

if __name__ == "__main__":
    app.run(
      host="0.0.0.0",
      port=int(PORT),
      ssl_context=(f'{BASE_PATH}/cert.pem',f'{BASE_PATH}/key.pem')
    )
