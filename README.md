
# 🎟️ Ticketing System

This project generates, prints, and scans tickets with QR codes. It uses Python, Flask, ReportLab, and PyPDF2. The system is now deployable both locally and via a public server using Nginx and HTTPS.

---

## 1. Prerequisites (for Developers)

### 📦 Local System Requirements (for generating tickets)

- Python 3.8+ installed (Windows or Linux)
- Git and OpenSSL (for creating SSL certs if needed)
- On Windows: allow inbound TCP port 8000 in Windows Firewall
- Make sure all devices are connected to the **same network** when testing locally

### 🌐 VPS Server Requirements (for public deployment)

- A public VPS (e.g. Hetzner Cloud) with Ubuntu 22.04
- A domain name (e.g. `tickets.danielnetzl.com`)
- Domain DNS pointing to your VPS (A record)
- `sudo` access via SSH (preferably using SSH keys)

---

## 2. Clone & Install (on any system)

```bash
git clone <repo-url> ticketing_system
cd ticketing_system
python -m venv venv
source venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt
````

---

## 3. Generate Tickets

1. Edit `config.py` and set:

   * `EVENT` (name of the event)
   * `N_TICKETS`
   * `BASE_PATH` and other layout config if needed
   * `URL = "tickets.danielnetzl.com"` (no prefix)

2. Place your event template PDF into `ticket_templates/` named as `{EVENT}.pdf`.

3. Generate everything (QR codes, PDFs, database, backup):

```bash
python generate_tickets.py
```

🎉 This creates:

* `events/{EVENT}/tickets.db`
* `qr_codes/` + `scan_page.png`
* `ticket_urls.csv`
* `tickets/` as printable PDFs
* A full backup in `bkp/{EVENT}`

---

## 4. Deploy to VPS with Nginx + HTTPS

### 🔐 A. Set up server

On your VPS:

```bash
sudo apt update
sudo apt install nginx python3-pip python3-venv git ufw -y
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 📁 B. Clone your project and set up Python

```bash
adduser tickets
usermod -aG sudo tickets
su - tickets
git clone <repo> ticketing_system
cd ticketing_system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 🚀 C. Run the app via systemd

Create `/etc/systemd/system/tickets.service`:

```ini
[Unit]
Description=Gunicorn for Ticket App
After=network.target

[Service]
User=tickets
Group=www-data
WorkingDirectory=/home/tickets/ticketing_system
Environment="PATH=/home/tickets/ticketing_system/venv/bin"
ExecStart=/home/tickets/ticketing_system/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reexec
sudo systemctl enable tickets
sudo systemctl start tickets
```

Check with:

```bash
sudo systemctl status tickets
```

---

### 🌐 D. Configure Nginx

Edit `/etc/nginx/sites-available/tickets`:

```nginx
server {
    listen 80;
    server_name tickets.danielnetzl.com;

    location / {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then:

```bash
sudo ln -s /etc/nginx/sites-available/tickets /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

### 🔒 E. Enable HTTPS with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx
```

Choose to redirect HTTP to HTTPS when prompted.

Now your app is securely available at:

```
https://tickets.danielnetzl.com/scan
```

---

## 5. Scanner Webpage

* URL: `https://tickets.danielnetzl.com/scan`
* QR code for this page is saved as `scan_page.png`
* Uses live camera access (requires HTTPS)
* 3-second delay between scans to avoid double scans

---

## 6. Instructions for Entrance Staff

This guide is for staff scanning tickets on phones/tablets.

### ✅ Setup

1. **Use Safari (iOS)** or **Chrome (Android)**. Ecosia, Firefox, DuckDuckGo won’t work.
2. Connect to mobile data or event Wi-Fi.
3. Scan the `scan_page.png` QR code and open the link in Safari/Chrome.
4. When prompted:

   * Allow camera access
   * Accept HTTPS certificate (if needed)

> Tip: Tap **Share → Zum Home-Bildschirm** to pin it as a full-screen app.

---

### 🎯 During the Event

* Hold the QR code clearly in the camera frame
* A message will appear:

  * ✅ **Ticket gültig** → allow entry
  * ❌ **Bereits verwendet** → reject
  * ❌ **Ungültig** → reject
* Wait 3 seconds before the next scan

---

### 🛠 Troubleshooting

* **Camera not available**: Make sure you use Safari or Chrome + HTTPS
* **Scan not detected**: Check lighting, glare, or focus
* **Tab closes**: Re-open the scan URL, clear browser cache if needed

---

## 7. Developer Notes

* Run `python generate_tickets.py` whenever you want to:

  * Create a new event
  * Regenerate QR codes
* All output is placed under `events/{EVENT}` and backed up
* The app auto-loads the correct database for the current event

---

## ✅ You're all set!

Access:

```
https://tickets.danielnetzl.com/scan
```

Support: Ask Daniel if anything breaks.