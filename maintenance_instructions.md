
# Deployment Manual for a New Ticketing Event

---

### 1. Log into the Server with VS Code

1. Open **VS Code**
2. Use the **Remote SSH** extension to connect via:

   ```
   ssh tickets@tickets.danielnetzl.com
   ```
3. Open the project folder:

   ```
   /home/tickets/ticketing_system
   ```

---

### 2. Update the `config.py`

In VS Code:

1. Open `config.py`
2. Update the following values:

   ```python
   EVENT = "new_event_2025"
   N_TICKETS = 1500
   ```

---

### 3. Generate New Tickets

In VS Code terminal:

```bash
su - tickets
cd ticketing_system/
source .venv/bin/activate
python generate_tickets.py
exit
```

This will:

* Create a new DB
* Generate QR codes
* Create PDFs
* Save a backup

---

### 4. Get Sudo Access to Restart the App

1. In case you are in the terminal, log out of `tickets` user:

   ```bash
   exit
   ```

2. In your Windows Terminal SSH in as **root** or use your SSH config:

   ```bash
   ssh root@tickets.danielnetzl.com
   ```

3. Restart the Gunicorn app:

   ```bash
   sudo systemctl restart tickets
   ```

4. Check status:

   ```bash
   sudo systemctl status tickets
   ```

You should see:

```
Active: active (running)
```

---

### 5. Test the New Event

Open:

```
https://tickets.danielnetzl.com/scan
```

Your QR codes will now point to:

```
https://tickets.danielnetzl.com/validate/<ticket_id>
```

To reset your validated tickets, visit:

```
https://tickets.danielnetzl.com/reset?key=
```