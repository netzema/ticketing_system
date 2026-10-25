# Wartungs- und Deployment-Anleitung

Stand: 25. Oktober 2026

Diese Anleitung beschreibt das aktuell produktive Jugend-Ticketsystem. Sie ersetzt
die frühere Anleitung für `tickets.danielnetzl.com` und den nicht mehr vorhandenen
Systemd-Dienst `tickets.service`.

## Aktuelles Setup

- Server/Hostname: `tickets`
- Benutzer und Projektpfad: `jugend`, `/home/jugend/tickets_jugend`
- Git-Branch: `main`
- Öffentliche Adresse: `https://jugend.netzldatasolutions.at`
- Anwendung: Flask hinter Gunicorn
- Gunicorn: vier Worker auf `127.0.0.1:8000`
- Reverse Proxy und TLS: Nginx mit Let's Encrypt
- Produktive Datenbank: `events/<EVENT>/tickets.db`; `<EVENT>` kommt aus `config.py`

Der normale Ablauf lautet:

> Änderungen prüfen -> Tests ausführen -> Datenbank sichern -> gezielt committen
> und pushen -> Gunicorn per `HUP` neu laden -> lokal und öffentlich kontrollieren

Ein `git push` allein stellt die laufenden Python-Worker nicht um. Erst das
Neuladen von Gunicorn aktiviert den neuen Code. Nginx muss bei gewöhnlichen
Python-, HTML-, CSS- oder JavaScript-Änderungen nicht neu geladen werden.

## 1. Vor einem normalen Deployment

In das Projekt wechseln und Zustand kontrollieren:

```bash
cd /home/jugend/tickets_jugend
git status --short
git branch --show-current
git fetch origin
git status -sb
```

Der aktive Branch muss `main` sein. Vorhandene fremde oder noch nicht zugehörige
Änderungen nicht verwerfen und nicht versehentlich mitcommitten. Ist der lokale
Branch bei sauberem Arbeitsverzeichnis hinter `origin/main`, kann er so
aktualisiert werden:

```bash
git pull --ff-only origin main
```

## 2. Änderungen testen

Die vollständige automatisierte Testsuite ausführen:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Anschließend Diff und Formatfehler kontrollieren:

```bash
git diff --check
git diff --stat
git diff
```

Zusätzlich die konkret geänderten Abläufe im Browser testen. Bei Änderungen an
Musikwünschen gehören dazu mindestens:

- Gastansicht und Absenden eines Wunsches
- Begrenzung auf drei Wünsche innerhalb des rollierenden Zeitfensters
- Pause ein- und ausschalten
- DJ-Anmeldung und -Abmeldung
- Statuswechsel sowie Verschieben der Wünsche nach oben und unten
- Darstellung auf Smartphone und Desktop

## 3. Produktionsdatenbank sichern

Vor Änderungen an Datenmodell, Ticketlogik oder Musikwünschen immer eine
konsistente SQLite-Sicherung anlegen. Die folgende Variante verwendet die
SQLite-Backup-API und kann bei laufender Anwendung ausgeführt werden:

```bash
.venv/bin/python - <<'PY'
from datetime import datetime
from pathlib import Path
import sqlite3

from config import BASE_PATH

source = Path(BASE_PATH) / "tickets.db"
backup_dir = Path("bkp") / f"deploy_{datetime.now():%Y%m%d_%H%M%S}"
backup_dir.mkdir(parents=True, exist_ok=False)
target = backup_dir / "tickets.db"

with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
    source_db.backup(target_db)

with sqlite3.connect(target) as backup_db:
    result = backup_db.execute("PRAGMA integrity_check").fetchone()[0]

if result != "ok":
    raise SystemExit(f"Sicherung ist fehlerhaft: {result}")

print(f"Sicherung erstellt und geprüft: {target}")
PY
```

Bei einer Schemaänderung die Migration zuerst auf einer Kopie dieser Sicherung
testen. Eine Datenbank niemals durch einfaches Kopieren über die laufende
Produktionsdatei zurückspielen.

## 4. Gezielt committen und pushen

Nur die Dateien aufnehmen, die wirklich zur Änderung gehören:

```bash
git add app.py templates/dj_dashboard.html tests/test_music_requests.py
git diff --cached --check
git diff --cached
git commit -m "Kurze Beschreibung der Änderung"
git push origin main
```

Die Dateiliste ist nur ein Beispiel und muss an die jeweilige Änderung angepasst
werden. Insbesondere `.env`, `events/`, `bkp/`, Zugangsdaten, Datenbanken und
lokale Screenshots nicht committen.

Nach dem Push prüfen:

```bash
git status -sb
git log -3 --oneline --decorate
```

`main` und `origin/main` sollten auf demselben Commit stehen.

## 5. Gunicorn ohne längeren Ausfall neu laden

Zuerst ausschließlich die Gunicorn-Prozesse dieses Projekts anzeigen:

```bash
ps -C gunicorn -o pid,ppid,user,lstart,args | rg '/home/jugend/tickets_jugend/'
```

Der Masterprozess ist die Zeile mit `PPID 1`. Seine PID vor dem nächsten Befehl
genau kontrollieren. Die Worker haben die Master-PID als PPID.

Den Master anschließend neu laden:

```bash
kill -HUP <GUNICORN-MASTER-PID>
```

Die PID nie fest in eine Anleitung oder ein Skript eintragen; sie kann sich
ändern. `HUP` lässt den Master laufen und ersetzt seine Worker kontrolliert durch
neue Prozesse, die den aktuellen Code importieren.

Danach erneut prüfen:

```bash
ps -C gunicorn -o pid,ppid,user,lstart,args | rg '/home/jugend/tickets_jugend/'
```

Es müssen vier aktuelle Worker unter demselben Master laufen. Ist kein passender
Master vorhanden, nicht blind einen weiteren Gunicorn-Prozess starten. Zuerst
Ursache und Portbelegung untersuchen.

`sudo systemctl restart tickets` gehört nicht mehr zu diesem Deployment: Auf dem
aktuellen System existiert kein `tickets.service`.

## 6. Nach dem Deployment prüfen

Zuerst den lokalen Gunicorn-Upstream testen:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: jugend.netzldatasolutions.at' http://127.0.0.1:8000/
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: jugend.netzldatasolutions.at' http://127.0.0.1:8000/musikwunsch
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: jugend.netzldatasolutions.at' http://127.0.0.1:8000/scan
curl -sS -o /dev/null -w '%{http_code}\n' -H 'Host: jugend.netzldatasolutions.at' http://127.0.0.1:8000/dj/musikwunsch/anmelden
```

Erwartet werden `302` für `/` und `200` für die drei Ansichten. Danach dieselben
öffentlichen Wege über HTTPS kontrollieren:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://jugend.netzldatasolutions.at/
curl -sS -o /dev/null -w '%{http_code}\n' https://jugend.netzldatasolutions.at/musikwunsch
curl -sS -o /dev/null -w '%{http_code}\n' https://jugend.netzldatasolutions.at/scan
curl -sS -o /dev/null -w '%{http_code}\n' https://jugend.netzldatasolutions.at/dj/musikwunsch/anmelden
```

Zum Abschluss die geänderten Funktionen manuell im Browser prüfen. Für den
Scanner ist zusätzlich der ausgelieferte Versions-Header hilfreich:

```bash
curl -sS -D - -o /dev/null https://jugend.netzldatasolutions.at/scan | rg 'HTTP/|[Xx]-Scanner-Version'
```

Die produktive Datenbank abschließend kontrollieren:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import sqlite3

from config import BASE_PATH

database = Path(BASE_PATH) / "tickets.db"
with sqlite3.connect(database) as connection:
    print(connection.execute("PRAGMA integrity_check").fetchone()[0])
PY
```

Die Ausgabe muss `ok` sein.

## 7. Umgebungsvariablen

Produktive Geheimnisse stehen ausschließlich in `/home/jugend/tickets_jugend/.env`.
Die Datei darf nicht in Git landen und sollte nur für den Benutzer `jugend`
lesbar sein:

```bash
chmod 600 /home/jugend/tickets_jugend/.env
```

Erforderliche beziehungsweise unterstützte Werte:

```dotenv
RESET_SECRET=<langes-zufälliges-geheimnis>
FLASK_SECRET_KEY=<anderes-langes-zufälliges-geheimnis>
DJ_PASSWORD=<passwort-für-leo>
SESSION_COOKIE_SECURE=1
MUSIC_REQUEST_COOLDOWN_SECONDS=600
```

`600` Sekunden entsprechen zehn Minuten. Ein Gerät darf drei Wünsche innerhalb
dieses rollierenden Zeitfensters senden. Sobald der älteste der drei Wünsche
älter als das Zeitfenster ist, wird wieder ein Platz frei.

Nach jeder Änderung an `.env` muss Gunicorn wie in Abschnitt 5 per `HUP` neu
geladen werden. Geheimnisse weder im Terminal-Output noch in Tickets, Commits
oder Screenshots veröffentlichen.

## 8. Rollback

Bei einem fehlerhaften Code-Deployment den problematischen Commit nicht mit
`git reset --hard` entfernen. Stattdessen nachvollziehbar zurücknehmen:

```bash
git log -5 --oneline
git revert <COMMIT-ID>
.venv/bin/python -m unittest discover -s tests -v
git push origin main
```

Danach Gunicorn erneut per `HUP` laden und die Prüfungen aus Abschnitt 6
wiederholen.

Eine Rücksicherung der Datenbank ist nur der letzte Ausweg, weil dabei seit der
Sicherung eingegangene Scans und Musikwünsche verloren gehen können. Vor einer
Rücksicherung erst Fehlerbild, Sicherungszeitpunkt und Datenverlust prüfen und
einen kontrollierten Wartungszeitraum festlegen.

## 9. Neues Event anlegen

Dieser Vorgang ist kein normales Deployment. `generate_tickets.py` löscht und
erstellt die Tabelle `tickets` im ausgewählten Event neu. Deshalb zuerst prüfen,
dass in `config.py` wirklich ein neuer, korrekter Eventname eingetragen ist.

1. In `config.py` mindestens `EVENT`, `N_TICKETS` und `URL` kontrollieren.
2. Die Druckvorlage als `ticket_templates/<EVENT>.pdf` hinterlegen.
3. Sicherstellen, dass `events/<EVENT>` keine noch benötigten Produktivdaten
   enthält.
4. Tickets, QR-Codes und CSV-Datei erzeugen:

   ```bash
   .venv/bin/python generate_tickets.py
   ```

5. Das zusammengeführte Ticket-PDF bei Bedarf separat erzeugen:

   ```bash
   .venv/bin/python pdf_tickets.py
   ```

6. Ausgaben unter `events/<EVENT>/` stichprobenartig prüfen, insbesondere
   Ticketanzahl, QR-Ziele und PDF-Layout.
7. Erst nach erfolgreicher Prüfung den normalen Deployment-Ablauf ab Abschnitt 2
   durchführen.

`generate_tickets.py` legt am Ende zusätzlich eine Kopie des erzeugten
Eventordners unter `bkp/` an. Diese nachträgliche Kopie ersetzt keine Sicherung
bereits vorhandener Daten vor dem Start des Generators.

## 10. Nginx

Die produktive Site-Konfiguration liegt unter `/etc/nginx/sites-available/jugend`
und ist in `/etc/nginx/sites-enabled/` aktiviert. Nginx leitet HTTPS-Anfragen an
`127.0.0.1:8000` weiter.

Nur bei einer tatsächlichen Änderung an der Nginx-Konfiguration:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Nginx nur neu laden, wenn `nginx -t` erfolgreich war.
