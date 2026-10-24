import concurrent.futures
from pathlib import Path
import sqlite3
import tempfile
import unittest

import app as music_app


class MusicRequestAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_directory.name) / "tickets.db")
        database = sqlite3.connect(self.database_path)
        database.execute(
            "CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY, scanned_at DATETIME)"
        )
        database.executemany(
            "INSERT INTO tickets(ticket_id, scanned_at) VALUES (?, NULL)",
            [("ticket-1",), ("ticket-2",)],
        )
        database.commit()
        database.close()

        self.original_database = music_app.DB
        music_app.DB = self.database_path
        music_app.app.config.update(
            TESTING=True,
            SECRET_KEY="test-session-secret",
            DJ_PASSWORD="leo-test-password",
            SESSION_COOKIE_SECURE=False,
            MUSIC_REQUEST_COOLDOWN_SECONDS=30,
        )
        self.client = music_app.app.test_client()

    def tearDown(self):
        music_app.DB = self.original_database
        self.temp_directory.cleanup()

    def database(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def login(self, client=None, password="leo-test-password"):
        client = client or self.client
        response = client.get("/dj/musikwunsch/anmelden")
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as current_session:
            csrf = current_session["csrf_token"]
        return client.post(
            "/dj/musikwunsch/anmelden",
            data={"csrf_token": csrf, "password": password},
            follow_redirects=False,
        )

    def dj_api_state(self, client=None):
        client = client or self.client
        response = client.get("/api/dj/musikwunsch")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def submit(self, title, artist="Test Artist", client=None, **extra):
        client = client or self.client
        client.get("/musikwunsch")
        return client.post(
            "/api/musikwunsch",
            json={"title": title, "artist": artist, "website": "", **extra},
        )

    def test_all_interfaces_are_branded_and_contain_no_middle_dots(self):
        public_paths = ["/", "/scan", "/musikwunsch", "/musikwunsch/qr"]
        for path in public_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                text = response.get_data(as_text=True)
                self.assertIn("Netzl Data Solutions", text)
                self.assertNotIn("·", text)

        login_page = self.client.get("/dj/musikwunsch/anmelden")
        self.assertIn("Netzl Data Solutions", login_page.get_data(as_text=True))
        self.assertNotIn("·", login_page.get_data(as_text=True))

        self.assertEqual(self.login().status_code, 302)
        dashboard = self.client.get("/dj/musikwunsch")
        self.assertEqual(dashboard.status_code, 200)
        dashboard_text = dashboard.get_data(as_text=True)
        self.assertIn("Netzl Data Solutions", dashboard_text)
        self.assertNotIn("·", dashboard_text)
        self.assertLess(
            dashboard_text.index('data-status="played"'),
            dashboard_text.index('data-status="later"'),
        )
        self.assertNotIn("Mal gewünscht - zuletzt", dashboard_text)

        ticket_page = self.client.get("/validate/unknown")
        self.assertIn("Netzl Data Solutions", ticket_page.get_data(as_text=True))
        self.assertNotIn("·", ticket_page.get_data(as_text=True))

    def test_scanner_keeps_bounded_camera_flow_and_uses_structured_results(self):
        response = self.client.get("/scan")
        self.assertEqual(response.status_code, 200)
        scanner = response.get_data(as_text=True)

        self.assertEqual(response.headers["X-Scanner-Version"], "2026-10-24.1")
        self.assertIn('data-scanner-version="2026-10-24.1"', scanner)
        self.assertIn('id="topbar"', scanner)
        self.assertIn('id="scan-delay"', scanner)
        self.assertIn('value="1500" selected', scanner)
        self.assertIn("oktoberfest-scanner-delay-ms", scanner)
        self.assertIn("getScanDelay()", scanner)
        self.assertIn("decodeFromVideoDevice", scanner)
        self.assertIn("isInsideScanWindow", scanner)
        self.assertIn('headers: { "Accept": "application/json" }', scanner)
        self.assertIn('result.status === "recent"', scanner)
        self.assertIn('result.status === "already_used"', scanner)
        self.assertNotIn("DOMParser", scanner)
        self.assertNotIn("response.text()", scanner)

    def test_guest_can_submit_and_duplicates_are_combined(self):
        first_client = music_app.app.test_client()
        second_client = music_app.app.test_client()

        first = self.submit("Dancing Queen", "ABBA", first_client)
        second = self.submit("  dancing   queen  ", "abba", second_client)

        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.get_json()["duplicate"])
        self.assertEqual(second.status_code, 201)
        self.assertTrue(second.get_json()["duplicate"])
        self.assertEqual(second.get_json()["request_count"], 2)

        database = self.database()
        rows = database.execute("SELECT * FROM music_requests").fetchall()
        database.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["song"], "Dancing Queen - ABBA")
        self.assertEqual(rows[0]["title"], "Dancing Queen")
        self.assertEqual(rows[0]["artist"], "ABBA")
        self.assertEqual(rows[0]["request_count"], 2)

    def test_matching_ignores_case_punctuation_and_accents(self):
        first_client = music_app.app.test_client()
        second_client = music_app.app.test_client()

        first = self.submit("Halo!", "Beyoncé", first_client)
        second = self.submit(" halo ", "BEYONCE", second_client)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertTrue(second.get_json()["duplicate"])
        self.assertEqual(second.get_json()["request_count"], 2)

    def test_same_device_is_rate_limited(self):
        first = self.submit("Song One", "Artist One")
        second = self.client.post(
            "/api/musikwunsch",
            json={"title": "Song Two", "artist": "Artist Two", "website": ""},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
        self.assertGreaterEqual(second.get_json()["retry_after"], 1)
        self.assertIn("Retry-After", second.headers)

    def test_invalid_input_honeypot_and_paused_state(self):
        self.client.get("/musikwunsch")
        self.assertEqual(
            self.client.post("/api/musikwunsch", json=["kein Objekt"]).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/musikwunsch",
                json={"title": {"value": "Song"}, "artist": "Artist"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/musikwunsch", json={"title": "", "artist": "Artist"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/musikwunsch", json={"title": "Song", "artist": ""}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/musikwunsch",
                json={"title": "x" * 101, "artist": "Artist"},
            ).status_code,
            400,
        )
        honeypot = self.client.post(
            "/api/musikwunsch",
            json={
                "title": "Spam Song",
                "artist": "Spam Artist",
                "website": "https://spam.invalid",
            },
        )
        self.assertEqual(honeypot.status_code, 201)

        database = self.database()
        music_app.ensure_music_request_schema(database)
        count = database.execute("SELECT COUNT(*) FROM music_requests").fetchone()[0]
        database.execute(
            "UPDATE music_request_settings SET value = '0' WHERE key = 'accepting_requests'"
        )
        database.commit()
        database.close()
        self.assertEqual(count, 0)

        paused_client = music_app.app.test_client()
        paused = self.submit("A valid song", "A valid artist", paused_client)
        self.assertEqual(paused.status_code, 423)
        page = paused_client.get("/musikwunsch").get_data(as_text=True)
        self.assertIn("Momentan pausiert", page)
        self.assertIn("disabled", page)

    def test_dj_routes_require_login_and_csrf(self):
        self.assertEqual(self.client.get("/dj/musikwunsch").status_code, 302)
        self.assertEqual(self.client.get("/api/dj/musikwunsch").status_code, 401)

        failed = self.login(password="wrong-password")
        self.assertEqual(failed.status_code, 200)
        self.assertIn("nicht korrekt", failed.get_data(as_text=True))

        logged_in = self.login()
        self.assertEqual(logged_in.status_code, 302)
        self.assertTrue(logged_in.headers["Location"].endswith("/dj/musikwunsch"))

        state = self.dj_api_state()
        self.assertTrue(state["accepting_requests"])
        self.assertEqual(state["requests"], [])

        no_csrf = self.client.post(
            "/api/dj/musikwunsch/annahme", json={"accepting": False}
        )
        self.assertEqual(no_csrf.status_code, 403)

        paused = self.client.post(
            "/api/dj/musikwunsch/annahme",
            json={"accepting": False},
            headers={"X-CSRF-Token": state["csrf_token"]},
        )
        self.assertEqual(paused.status_code, 200)
        self.assertFalse(paused.get_json()["accepting_requests"])

    def test_dj_can_move_and_undo_requests(self):
        guest = music_app.app.test_client()
        created = self.submit("September", "Earth Wind and Fire", guest)
        self.assertEqual(created.status_code, 201)

        self.assertEqual(self.login().status_code, 302)
        state = self.dj_api_state()
        request_item = state["requests"][0]
        csrf = state["csrf_token"]

        moved = self.client.post(
            f"/api/dj/musikwunsch/{request_item['id']}/status",
            json={"status": "later"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.get_json()["previous_status"], "new")
        self.assertEqual(moved.get_json()["request"]["status"], "later")

        undone = self.client.post(
            f"/api/dj/musikwunsch/{request_item['id']}/status",
            json={"status": "new"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.get_json()["request"]["status"], "new")

        invalid = self.client.post(
            f"/api/dj/musikwunsch/{request_item['id']}/status",
            json={"status": "unknown"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_played_song_can_be_requested_again_as_new(self):
        self.assertEqual(self.submit("Angels", "Robbie Williams").status_code, 201)
        self.assertEqual(self.login().status_code, 302)
        state = self.dj_api_state()
        request_item = state["requests"][0]
        played = self.client.post(
            f"/api/dj/musikwunsch/{request_item['id']}/status",
            json={"status": "played"},
            headers={"X-CSRF-Token": state["csrf_token"]},
        )
        self.assertEqual(played.status_code, 200)

        another_guest = music_app.app.test_client()
        repeated = self.submit("angels", "robbie williams", another_guest)
        self.assertEqual(repeated.status_code, 201)
        self.assertFalse(repeated.get_json()["duplicate"])

        database = self.database()
        rows = database.execute(
            "SELECT status FROM music_requests ORDER BY id"
        ).fetchall()
        database.close()
        self.assertEqual([row["status"] for row in rows], ["played", "new"])

    def test_dj_can_delete_all_only_with_exact_confirmation(self):
        self.assertEqual(self.submit("One More Time", "Daft Punk").status_code, 201)
        self.assertEqual(self.login().status_code, 302)
        csrf = self.dj_api_state()["csrf_token"]

        rejected = self.client.post(
            "/api/dj/musikwunsch/alle-loeschen",
            json={"confirmation": "löschen"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(rejected.status_code, 400)

        deleted = self.client.post(
            "/api/dj/musikwunsch/alle-loeschen",
            json={"confirmation": "ALLE LÖSCHEN"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.dj_api_state()["requests"], [])

    def test_login_is_temporarily_blocked_after_repeated_failures(self):
        page = self.client.get("/dj/musikwunsch/anmelden")
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as current_session:
            csrf = current_session["csrf_token"]

        for _ in range(5):
            response = self.client.post(
                "/dj/musikwunsch/anmelden",
                data={"csrf_token": csrf, "password": "wrong"},
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            "/dj/musikwunsch/anmelden",
            data={"csrf_token": csrf, "password": "leo-test-password"},
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertIn("zehn Minuten", blocked.get_data(as_text=True))

    def test_dj_password_supports_non_ascii_characters(self):
        music_app.app.config["DJ_PASSWORD"] = "Löwe-singt-über-Österreich"

        response = self.login(password="Löwe-singt-über-Österreich")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/dj/musikwunsch"))

    def test_qr_code_is_a_png(self):
        response = self.client.get("/musikwunsch/qr-code.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(response.data), 500)

    def test_existing_ticket_validation_still_works(self):
        headers = {"Accept": "application/json"}
        first = self.client.get("/validate/ticket-1", headers=headers)
        second = self.client.get("/validate/ticket-1", headers=headers)
        invalid = self.client.get("/validate/not-a-ticket", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["status"], "valid")
        self.assertEqual(second.get_json()["status"], "recent")
        self.assertEqual(invalid.get_json()["status"], "invalid")

        database = self.database()
        database.execute(
            "UPDATE tickets SET scanned_at = ? WHERE ticket_id = ?",
            ("2000-01-01 00:00:00", "ticket-1"),
        )
        database.commit()
        database.close()

        used = self.client.get("/validate/ticket-1", headers=headers)
        self.assertEqual(used.status_code, 200)
        self.assertEqual(used.get_json()["status"], "already_used")

    def test_concurrent_duplicate_submissions_remain_one_request(self):
        music_app.app.test_client().get("/musikwunsch")

        def submit_from_new_device(song_data):
            client = music_app.app.test_client()
            title, artist = song_data
            return self.submit(title, artist, client).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            status_codes = list(
                executor.map(
                    submit_from_new_device,
                    [
                        ("Mr. Brightside", "The Killers"),
                        ("mr brightside", "the killers"),
                    ],
                )
            )

        self.assertEqual(status_codes, [201, 201])
        database = self.database()
        rows = database.execute(
            "SELECT request_count FROM music_requests"
        ).fetchall()
        database.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["request_count"], 2)

    def test_song_text_is_returned_as_data_not_rendered_into_dashboard(self):
        dangerous = '<script>alert("x")</script>'
        self.assertEqual(self.submit(dangerous, "Safe Artist").status_code, 201)
        self.assertEqual(self.login().status_code, 302)
        state = self.dj_api_state()
        self.assertEqual(state["requests"][0]["title"], dangerous)
        dashboard = self.client.get("/dj/musikwunsch").get_data(as_text=True)
        self.assertNotIn(dangerous, dashboard)
        self.assertIn("song.textContent = item.title || item.song", dashboard)

    def test_existing_music_request_schema_is_migrated(self):
        database = self.database()
        database.execute(
            """
            CREATE TABLE music_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song TEXT NOT NULL,
                normalized_song TEXT NOT NULL,
                status TEXT NOT NULL,
                request_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_requested_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        database.execute(
            """
            INSERT INTO music_requests(
                song, normalized_song, status, request_count,
                created_at, last_requested_at, updated_at
            ) VALUES ('Legacy Song - Legacy Artist', 'legacysonglegacyartist', 'new', 1,
                      '2026-10-24T00:00:00+00:00', '2026-10-24T00:00:00+00:00',
                      '2026-10-24T00:00:00+00:00')
            """
        )
        database.commit()

        music_app.ensure_music_request_schema(database)
        columns = {
            row[1] for row in database.execute("PRAGMA table_info(music_requests)")
        }
        row = database.execute("SELECT * FROM music_requests").fetchone()
        database.close()

        self.assertTrue(
            {"title", "artist", "normalized_title", "normalized_artist"}.issubset(columns)
        )
        self.assertEqual(row["title"], "Legacy Song - Legacy Artist")
        self.assertEqual(row["artist"], "")


if __name__ == "__main__":
    unittest.main()
