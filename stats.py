import polars as pl
import sqlite3
from config import BASE_PATH
from dotenv import load_dotenv

print(load_dotenv())
DB = f"{BASE_PATH}/tickets.db"

conn = sqlite3.connect(DB)
c = conn.cursor()

df = pl.read_database("SELECT * FROM tickets", conn)

total = df.height
n_scanned = df.filter(pl.col("scanned_at").is_not_null()).height
print(f"{total=}")
print(f"{n_scanned=}")

df = df.with_columns([
    pl.col("scanned_at").str.strptime(pl.Datetime).dt.convert_time_zone(time_zone="Europe/Berlin")
])
avg_arrival = df["scanned_at"].mean()
min_arrival = df["scanned_at"].min()
max_arrival = df["scanned_at"].max()
print(f"{avg_arrival=}")
print(f"{min_arrival=}")
print(f"{max_arrival=}")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


pdf = df.to_pandas()
pdf["scanned_at_hr"] = pdf["scanned_at"].dt.floor("h")
pdf["scanned_at_min"] = pdf["scanned_at"].dt.floor("5min")
scans_per_minute = pdf.groupby("scanned_at_min").size()
scans_per_hour = pdf.groupby("scanned_at_hr").size()

plt.figure(figsize=(12, 6))
scans_per_minute.plot(kind="bar", width=1.0, color="skyblue")

plt.title("Verteilung der Eintrittszeiten")
plt.xlabel("Zeitpunkt (auf Minute gerundet)")
plt.ylabel("Anzahl gescannter Tickets")
plt.xticks(rotation=90)
plt.tight_layout()

ax = plt.gca()
PLOT_PATH = f"{BASE_PATH}/entry_distribution_minute.png"
plt.savefig(PLOT_PATH, dpi=300)
plt.close()

plt.figure(figsize=(12, 6))
scans_per_hour.plot(kind="bar", width=1.0, color="skyblue")

plt.title("Verteilung der Eintrittszeiten")
plt.xlabel("Zeitpunkt (auf Stunde gerundet)")
plt.ylabel("Anzahl gescannter Tickets")
plt.xticks(rotation=90)
plt.tight_layout()

ax = plt.gca()
PLOT_PATH = f"{BASE_PATH}/entry_distribution_hour.png"
plt.savefig(PLOT_PATH, dpi=300)
plt.close()

print(f"Plots saved to {PLOT_PATH}")