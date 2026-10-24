import concurrent.futures
from datetime import timedelta
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
            MUSIC_REQUEST_COOLDOWN_SECONDS=600,
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
        public_paths = ["/scan", "/musikwunsch"]
        for path in public_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                text = response.get_data(as_text=True)
                self.assertIn("Netzl Data Solutions", text)
                self.assertNotIn("·", text)
                self.assertIn('rel="icon" type="image/svg+xml" href="/static/favicon.svg"', text)
                self.assertIn('rel="apple-touch-icon" href="/static/apple-touch-icon.png"', text)

        login_page = self.client.get("/dj/musikwunsch/anmelden")
        login_text = login_page.get_data(as_text=True)
        self.assertIn("Netzl Data Solutions", login_text)
        self.assertNotIn("·", login_text)
        self.assertIn('/static/favicon.svg', login_text)
        self.assertIn('/static/apple-touch-icon.png', login_text)

        self.assertEqual(self.login().status_code, 302)
        dashboard = self.client.get("/dj/musikwunsch")
        self.assertEqual(dashboard.status_code, 200)
        dashboard_text = dashboard.get_data(as_text=True)
        self.assertIn("Netzl Data Solutions", dashboard_text)
        self.assertNotIn("·", dashboard_text)
        self.assertIn('/static/favicon.svg', dashboard_text)
        self.assertIn('/static/apple-touch-icon.png', dashboard_text)
        self.assertNotIn("QR-Seite", dashboard_text)
        self.assertNotIn("/musikwunsch/qr", dashboard_text)
        self.assertLess(
            dashboard_text.index('data-status="played"'),
            dashboard_text.index('data-status="later"'),
        )
        self.assertNotIn("Mal gewünscht - zuletzt", dashboard_text)

        ticket_page = self.client.get("/validate/unknown")
        ticket_text = ticket_page.get_data(as_text=True)
        self.assertIn("Netzl Data Solutions", ticket_text)
        self.assertNotIn("·", ticket_text)
        self.assertIn('/static/favicon.svg', ticket_text)
        self.assertIn('/static/apple-touch-icon.png', ticket_text)

    def test_subdomain_root_redirects_to_company_website(self):
        response = self.client.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://www.netzldatasolutions.at/")

    def test_icon_assets_are_served(self):
        favicon = self.client.get("/static/favicon.svg")
        apple_icon = self.client.get("/static/apple-touch-icon.png")

        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon.mimetype, "image/svg+xml")
        self.assertTrue(favicon.data.startswith(b"<svg"))
        self.assertEqual(apple_icon.status_code, 200)
        self.assertEqual(apple_icon.mimetype, "image/png")
        self.assertTrue(apple_icon.data.startswith(b"\x89PNG\r\n\x1a\n"))
        favicon.close()
        apple_icon.close()

    def test_guest_page_is_compact_and_has_clear_feedback(self):
        page = self.client.get("/musikwunsch").get_data(as_text=True)

        self.assertNotIn("Wünsche geöffnet", page)
        self.assertNotIn("music-mark", page)
        self.assertNotIn("♫", page)
        self.assertIn('id="success-overlay"', page)
        self.assertIn('class="success-check"', page)
        self.assertIn("Musikwunsch gesendet", page)
        self.assertIn("}, 1800);", page)
        self.assertIn('id="paused-dialog"', page)
        self.assertIn("#request-form { position:relative; margin-top:20px; }", page)
        self.assertIn(
            'href="https://www.netzldatasolutions.at/" target="_blank" rel="noopener">Netzl Data Solutions</a>',
            page,
        )
        self.assertLess(
            page.index('id="submit-button"'),
            page.index("Dein Wunsch ist keine Garantie"),
        )

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
        self.assertIn("grid-column:3", scanner)
        self.assertIn("justify-self:end", scanner)
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
        second = self.submit("Song Two", "Artist Two")
        third = self.submit("Song Three", "Artist Three")
        fourth = self.client.post(
            "/api/musikwunsch",
            json={"title": "Song Four", "artist": "Artist Four", "website": ""},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.get_json()["remaining_requests"], 2)
        self.assertFalse(first.get_json()["cooldown_active"])
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.get_json()["remaining_requests"], 1)
        self.assertEqual(third.status_code, 201)
        self.assertEqual(third.get_json()["remaining_requests"], 0)
        self.assertTrue(third.get_json()["cooldown_active"])
        self.assertGreaterEqual(third.get_json()["retry_after"], 599)
        self.assertLessEqual(third.get_json()["retry_after"], 600)
        self.assertEqual(fourth.status_code, 429)
        self.assertGreaterEqual(fourth.get_json()["retry_after"], 599)
        self.assertIn("Retry-After", fourth.headers)

        blocked_page = self.client.get("/musikwunsch").get_data(as_text=True)
        self.assertIn("const deviceRetryAfter = ", blocked_page)
        self.assertIn("Weiterer Wunsch in ${minutes}:${secondsPart}", blocked_page)

        database = self.database()
        database.execute(
            "UPDATE music_request_submissions SET submitted_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
        database.execute(
            """
            UPDATE music_request_clients
            SET submission_count = 3, blocked_until = ?
            """,
            ("2999-01-01T00:00:00+00:00",),
        )
        database.commit()
        database.close()

        after_pause = self.submit("Song Five", "Artist Five")
        self.assertEqual(after_pause.status_code, 201)
        self.assertEqual(after_pause.get_json()["remaining_requests"], 2)
        self.assertFalse(after_pause.get_json()["cooldown_active"])

    def test_request_limit_only_counts_the_rolling_ten_minute_window(self):
        first = self.submit("Early Song One", "Early Artist One")
        second = self.submit("Early Song Two", "Early Artist Two")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        database = self.database()
        database.execute(
            "UPDATE music_request_submissions SET submitted_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
        database.commit()
        database.close()

        third = self.submit("Later Song Three", "Later Artist Three")
        fourth = self.submit("Later Song Four", "Later Artist Four")
        fifth = self.submit("Later Song Five", "Later Artist Five")
        sixth = self.client.post(
            "/api/musikwunsch",
            json={
                "title": "Later Song Six",
                "artist": "Later Artist Six",
                "website": "",
            },
        )

        self.assertEqual(third.status_code, 201)
        self.assertEqual(third.get_json()["remaining_requests"], 2)
        self.assertEqual(fourth.status_code, 201)
        self.assertEqual(fourth.get_json()["remaining_requests"], 1)
        self.assertEqual(fifth.status_code, 201)
        self.assertEqual(fifth.get_json()["remaining_requests"], 0)
        self.assertEqual(sixth.status_code, 429)

    def test_rolling_limit_expires_from_the_oldest_recent_request(self):
        self.assertEqual(self.submit("Song One", "Artist One").status_code, 201)
        self.assertEqual(self.submit("Song Two", "Artist Two").status_code, 201)
        self.assertEqual(self.submit("Song Three", "Artist Three").status_code, 201)

        nine_minutes_ago = music_app.utc_timestamp(
            music_app.utc_now() - timedelta(minutes=9)
        )
        database = self.database()
        oldest_id = database.execute(
            "SELECT MIN(id) FROM music_request_submissions"
        ).fetchone()[0]
        database.execute(
            "UPDATE music_request_submissions SET submitted_at = ? WHERE id = ?",
            (nine_minutes_ago, oldest_id),
        )
        database.commit()
        database.close()

        still_blocked = self.client.post(
            "/api/musikwunsch",
            json={"title": "Song Four", "artist": "Artist Four", "website": ""},
        )
        self.assertEqual(still_blocked.status_code, 429)
        self.assertGreaterEqual(still_blocked.get_json()["retry_after"], 59)
        self.assertLessEqual(still_blocked.get_json()["retry_after"], 60)

        eleven_minutes_ago = music_app.utc_timestamp(
            music_app.utc_now() - timedelta(minutes=11)
        )
        database = self.database()
        database.execute(
            "UPDATE music_request_submissions SET submitted_at = ? WHERE id = ?",
            (eleven_minutes_ago, oldest_id),
        )
        database.commit()
        database.close()

        allowed = self.submit("Song Four", "Artist Four")
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(allowed.get_json()["remaining_requests"], 0)

    def test_concurrent_requests_cannot_exceed_the_window_limit(self):
        self.assertEqual(self.submit("First Song", "First Artist").status_code, 201)
        self.assertEqual(self.submit("Second Song", "Second Artist").status_code, 201)
        guest_cookie = self.client.get_cookie(music_app.GUEST_COOKIE_NAME).value

        def submit_from_same_device(song_data):
            client = music_app.app.test_client()
            client.set_cookie(music_app.GUEST_COOKIE_NAME, guest_cookie)
            title, artist = song_data
            return client.post(
                "/api/musikwunsch",
                json={"title": title, "artist": artist, "website": ""},
            ).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            status_codes = list(
                executor.map(
                    submit_from_same_device,
                    [
                        ("Third Song", "Third Artist"),
                        ("Fourth Song", "Fourth Artist"),
                    ],
                )
            )

        self.assertEqual(sorted(status_codes), [201, 429])
        database = self.database()
        submission_count = database.execute(
            "SELECT COUNT(*) FROM music_request_submissions"
        ).fetchone()[0]
        database.close()
        self.assertEqual(submission_count, 3)

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
        self.assertIn("Musikwünsche pausiert", page)
        self.assertIn("if (!requestsInitiallyOpen) showPausedDialog();", page)
        self.assertIn("const requestsInitiallyOpen = false;", page)
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

    def test_dj_can_persist_custom_request_order(self):
        self.assertEqual(self.submit("First Song", "First Artist").status_code, 201)
        self.assertEqual(self.submit("Second Song", "Second Artist").status_code, 201)
        self.assertEqual(self.submit("Third Song", "Third Artist").status_code, 201)
        self.assertEqual(self.login().status_code, 302)

        state = self.dj_api_state()
        current = [item for item in state["requests"] if item["status"] == "new"]
        self.assertEqual(
            [item["title"] for item in current],
            ["Third Song", "Second Song", "First Song"],
        )
        desired_ids = [current[2]["id"], current[0]["id"], current[1]["id"]]

        reordered = self.client.post(
            "/api/dj/musikwunsch/reihenfolge",
            json={"status": "new", "request_ids": desired_ids},
            headers={"X-CSRF-Token": state["csrf_token"]},
        )

        self.assertEqual(reordered.status_code, 200)
        self.assertEqual(
            [item["id"] for item in reordered.get_json()["requests"]], desired_ids
        )
        refreshed = [
            item
            for item in self.dj_api_state()["requests"]
            if item["status"] == "new"
        ]
        self.assertEqual([item["id"] for item in refreshed], desired_ids)
        self.assertEqual([item["sort_order"] for item in refreshed], [0, 1, 2])

        another_guest = music_app.app.test_client()
        newest = self.submit("Newest Song", "Newest Artist", another_guest)
        self.assertEqual(newest.status_code, 201)
        with_new_request = [
            item
            for item in self.dj_api_state()["requests"]
            if item["status"] == "new"
        ]
        self.assertEqual(with_new_request[0]["title"], "Newest Song")
        self.assertEqual(
            [item["id"] for item in with_new_request[1:]], desired_ids
        )

    def test_dj_order_endpoint_rejects_unsafe_or_stale_lists(self):
        self.assertEqual(self.submit("One Song", "One Artist").status_code, 201)
        self.assertEqual(self.submit("Two Song", "Two Artist").status_code, 201)
        self.assertEqual(self.login().status_code, 302)
        state = self.dj_api_state()
        request_ids = [item["id"] for item in state["requests"]]

        missing_csrf = self.client.post(
            "/api/dj/musikwunsch/reihenfolge",
            json={"status": "new", "request_ids": request_ids},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        headers = {"X-CSRF-Token": state["csrf_token"]}
        duplicate = self.client.post(
            "/api/dj/musikwunsch/reihenfolge",
            json={"status": "new", "request_ids": [request_ids[0], request_ids[0]]},
            headers=headers,
        )
        self.assertEqual(duplicate.status_code, 400)

        boolean_id = self.client.post(
            "/api/dj/musikwunsch/reihenfolge",
            json={"status": "new", "request_ids": [True, request_ids[1]]},
            headers=headers,
        )
        self.assertEqual(boolean_id.status_code, 400)

        stale = self.client.post(
            "/api/dj/musikwunsch/reihenfolge",
            json={"status": "new", "request_ids": request_ids[:1]},
            headers=headers,
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIn("neu geladen", stale.get_json()["error"])

    def test_status_changes_use_predictable_queue_positions(self):
        self.assertEqual(self.submit("Alpha Song", "Alpha Artist").status_code, 201)
        self.assertEqual(self.submit("Beta Song", "Beta Artist").status_code, 201)
        self.assertEqual(self.login().status_code, 302)
        state = self.dj_api_state()
        by_title = {item["title"]: item for item in state["requests"]}
        headers = {"X-CSRF-Token": state["csrf_token"]}

        for title in ("Beta Song", "Alpha Song"):
            response = self.client.post(
                f"/api/dj/musikwunsch/{by_title[title]['id']}/status",
                json={"status": "later"},
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
        later = [
            item
            for item in self.dj_api_state()["requests"]
            if item["status"] == "later"
        ]
        self.assertEqual([item["title"] for item in later], ["Beta Song", "Alpha Song"])

        for title in ("Beta Song", "Alpha Song"):
            response = self.client.post(
                f"/api/dj/musikwunsch/{by_title[title]['id']}/status",
                json={"status": "played"},
                headers=headers,
            )
            self.assertEqual(response.status_code, 200)
        played = [
            item
            for item in self.dj_api_state()["requests"]
            if item["status"] == "played"
        ]
        self.assertEqual([item["title"] for item in played], ["Alpha Song", "Beta Song"])

    def test_dj_dashboard_exposes_touch_and_keyboard_reordering(self):
        self.assertEqual(self.login().status_code, 302)
        dashboard = self.client.get("/dj/musikwunsch").get_data(as_text=True)

        self.assertIn('handle.className = "drag-handle"', dashboard)
        self.assertIn('handle.addEventListener("pointerdown"', dashboard)
        self.assertIn('handle.addEventListener("keydown"', dashboard)
        self.assertIn('document.addEventListener("pointermove"', dashboard)
        self.assertIn('document.addEventListener("pointerup"', dashboard)
        self.assertIn('["ArrowUp", "ArrowDown"]', dashboard)
        self.assertIn("touch-action:none", dashboard)
        self.assertIn("/api/dj/musikwunsch/reihenfolge", dashboard)
        self.assertIn("setPointerCapture", dashboard)

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
        database = self.database()
        self.assertEqual(
            database.execute(
                "SELECT COUNT(*) FROM music_request_submissions"
            ).fetchone()[0],
            0,
        )
        database.close()

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

    def test_qr_print_routes_are_removed(self):
        self.assertEqual(self.client.get("/musikwunsch/qr").status_code, 404)
        self.assertEqual(self.client.get("/musikwunsch/qr-code.png").status_code, 404)

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
            CREATE TABLE music_request_clients (
                client_hash TEXT PRIMARY KEY,
                last_submitted_at TEXT NOT NULL
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
        client_columns = {
            row[1]
            for row in database.execute("PRAGMA table_info(music_request_clients)")
        }
        submission_columns = {
            row[1]
            for row in database.execute(
                "PRAGMA table_info(music_request_submissions)"
            )
        }
        row = database.execute("SELECT * FROM music_requests").fetchone()
        database.close()

        self.assertTrue(
            {
                "title",
                "artist",
                "normalized_title",
                "normalized_artist",
                "sort_order",
            }.issubset(columns)
        )
        self.assertTrue({"submission_count", "blocked_until"}.issubset(client_columns))
        self.assertEqual(
            submission_columns,
            {"id", "client_hash", "submitted_at"},
        )
        self.assertEqual(row["title"], "Legacy Song - Legacy Artist")
        self.assertEqual(row["artist"], "")
        self.assertEqual(row["sort_order"], 0)


if __name__ == "__main__":
    unittest.main()
