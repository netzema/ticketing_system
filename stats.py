import polars as pl
import sqlite3
from datetime import datetime
from config import BASE_PATH, PORT, URL, HOST
from dotenv import load_dotenv
import os

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