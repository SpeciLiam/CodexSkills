import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))


class CaptureSourceParsers(unittest.TestCase):
    def setUp(self):
        import capture_web
        importlib.reload(capture_web)
        self.capture_web = capture_web

    def test_parse_pm_udr_units(self):
        html = """
        <html><head>
          <meta property="place:location:latitude" content="37.3930734" />
          <meta property="place:location:longitude" content="-121.9484431" />
        </head><body>
        <script>
        window.udr.jsonObjPropertyViewModel = {
          "propertyName": "River Terrace",
          "apartmentsPageUrl": "/apartments-pricing/",
          "leaseTermsRangeText": "3 - 14 month lease terms available",
          "floorPlans": [{
            "id": 107638,
            "Name": "Cascal",
            "bedRooms": 1,
            "bathRooms": 1.0,
            "sqFtMin": 719,
            "units": [{
              "isAvailable": true,
              "apartmentId": 13652214,
              "marketingName": "133",
              "availableDate": "/Date(1787443200000)/",
              "earliestMoveInDate": "/Date(1787616000000)/",
              "bedrooms": 1,
              "bathrooms": 1.0,
              "sqFt": 719,
              "lowestRent": {"baseRent": 3536.0}
            }]
          }]
        };
        </script></body></html>
        """
        records = self.capture_web.parse_pm_udr(html, {
            "name": "River Terrace",
            "market_hint": "Santa Clara",
            "city": "Santa Clara",
            "address": "730 Agnew Road, Santa Clara, CA 95054",
            "url": "https://www.udr.com/san-francisco-bay-area-apartments/santa-clara/river-terrace/apartments-pricing/",
        })
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "River Terrace")
        self.assertEqual(records[0]["listing_key"], "pm-river-terrace-13652214")
        self.assertEqual(records[0]["rent"], "$3,536")
        self.assertEqual(records[0]["beds"], "1 bd")
        self.assertEqual(records[0]["available"], "2026-08-25")
        self.assertEqual(records[0]["lat"], "37.3930734")
        self.assertEqual(records[0]["lng"], "-121.9484431")

    def test_parse_rent_next_data_floorplans(self):
        state = {"props": {"pageProps": {"pageData": {"location": {"listingSearch": {"listings": [{
            "id": "lc5901643",
            "name": "Normandy Park Apartments",
            "urlPathname": "/apartment/normandy-park-apartments-santa-clara-ca-lc5901643",
            "location": {"lat": 37.339194, "lng": -121.93953, "city": "Santa Clara"},
            "floorPlans": [{
                "bedCount": 2,
                "bathCount": 1,
                "availableDate": "2026-07-17T00:00:00.000Z",
                "priceRange": {"min": 3450, "max": 3450},
                "units": [{"rent": "$3,450"}],
            }],
        }]}}}}}}
        records = self.capture_web.parse_rent_next_data(state, {
            "name": "Rent.com",
            "market_hint": "Santa Clara",
        })
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["listing_key"], "rent-lc5901643-0")
        self.assertEqual(records[0]["rent"], "$3,450")
        self.assertEqual(records[0]["beds"], "2 bd")
        self.assertEqual(records[0]["available"], "2026-07-17")
        self.assertEqual(records[0]["lat"], "37.339194")

    def test_parse_rent_next_data_applies_min_bedroom_gate(self):
        state = {
            "props": {"pageProps": {"pageData": {"location": {"listingSearch": {
                "listings": [{
                    "id": "building-1", "name": "Building", "urlPathname": "/building-1",
                    "floorPlans": [
                        {"bedCount": 2, "bathCount": 1, "priceRange": {"min": 3000}},
                        {"id": "five-bed", "bedCount": 5, "bathCount": 3, "priceRange": {"min": 9000}},
                    ],
                }],
            }}}}},
        }
        records = self.capture_web.parse_rent_next_data(state, {
            "name": "Rent.com", "market_hint": "San Francisco", "min_bedrooms": 5,
        })
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["beds"], "5 bd")
        self.assertEqual(records[0]["listing_key"], "rent-building-1-five-bed")

    def test_title_bed_count_avoids_price_and_bath_bleed(self):
        cases = [
            ("$5,200 / 6br house", 6),
            ("Huge 5 bedroom 3 bath Victorian", 5),
            ("$5200 2bd", 2),
            ("5 bath 3 bedroom", 3),
            ("Sunny group house near Dolores Park", None),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(self.capture_web.title_bed_count(title), expected)

    def test_craigslist_title_fills_missing_beds_bucket(self):
        payload = {"data": {"decode": {"minPostingId": 1000}, "items": [
            [1, "Huge 5 bedroom 3 bath Victorian", 5200, "$5,200", "1:0~37.76~-122.42", [6, "huge-5-bedroom-3-bath-victorian"]]
        ]}}
        records = self.capture_web.parse_craigslist(payload, {
            "name": "Craigslist",
            "market_hint": "SF SoMa/South Beach/Mission Bay",
            "subarea": "sfc",
            "category": "apa",
        }, {})
        self.assertEqual(records[0]["beds"], "5 bd")


    def test_parse_redfin_ldjson_joins_accommodation_and_product(self):
        html = """
        <script type="application/ld+json">{"@context":"http://schema.org","@type":"Organization","name":"Redfin"}</script>
        <script type="application/ld+json">[
          {"@context":"http://schema.org","@type":"Accommodation",
           "name":"City Gate - 5608 Stevens Creek Blvd, Cupertino, CA, 95014",
           "url":"https://www.redfin.com/CA/Cupertino/City-Gate/apartment/177360368",
           "address":{"@type":"PostalAddress","streetAddress":"5608 Stevens Creek Blvd","addressLocality":"Cupertino"},
           "geo":{"@type":"GeoCoordinates","latitude":37.3225724,"longitude":-122.0018051},
           "numberOfRooms":"1-3"},
          {"@context":"http://schema.org","@type":"Product",
           "name":"City Gate - 5608 Stevens Creek Blvd",
           "offers":{"@type":"Offer","price":"3231","priceCurrency":"USD"},
           "url":"https://www.redfin.com/CA/Cupertino/City-Gate/apartment/177360368"}
        ]</script>
        """
        records = self.capture_web.parse_redfin_ldjson(html, {"market_hint": "Santa Clara"})
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["listing_key"], "redfin-177360368")
        self.assertEqual(rec["rent"], "$3231")
        self.assertEqual(rec["beds"], "1-3")
        self.assertEqual(rec["city"], "Cupertino")
        self.assertEqual(rec["lat"], "37.3225724")

    def test_parse_redfin_ldjson_empty_on_challenge_page(self):
        records = self.capture_web.parse_redfin_ldjson("<html><body>checking your browser</body></html>", {})
        self.assertEqual(records, [])

    def test_parse_rss_atom_entries(self):
        import run as run_mod
        importlib.reload(run_mod)
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>search results</title>
          <entry>
            <title>Looking for sublet or room to share</title>
            <link href="https://www.reddit.com/r/bayarea/comments/1uii6lb/looking_for_sublet/"/>
            <content type="html">&lt;a href="x"&gt;submitted by&lt;/a&gt; $1,400/mo near Caltrain</content>
            <published>2026-07-01T18:00:00+00:00</published>
          </entry>
        </feed>"""
        records = run_mod.parse_rss_body(body, "Reddit", "")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["title"], "Looking for sublet or room to share")
        self.assertEqual(rec["url"], "https://www.reddit.com/r/bayarea/comments/1uii6lb/looking_for_sublet/")
        self.assertIn("$1,400/mo near Caltrain", rec["description"])
        self.assertNotIn("<a", rec["description"])
        self.assertEqual(rec["posted"], "2026-07-01T18:00:00+00:00")

    def test_rss_url_preserves_dot_rss_paths(self):
        import run as run_mod
        importlib.reload(run_mod)
        url = "https://www.reddit.com/r/bayarea/search.rss?q=sublet&restrict_sr=on&sort=new"
        self.assertEqual(run_mod._rss_url(url), url)

    def test_reddit_rss_keeps_recent_offers_only(self):
        import run as run_mod
        importlib.reload(run_mod)
        records = [
            {"source": "Reddit", "title": "Furnished 1BR apartment sublet in Nob Hill",
             "url": "https://reddit.test/good", "posted": "2026-07-08T12:00:00+00:00"},
            {"source": "Reddit", "title": "Whole house water filter recommendations",
             "url": "https://reddit.test/noise", "posted": "2026-07-08T12:00:00+00:00"},
            {"source": "Reddit", "title": "Room for rent near Caltrain",
             "url": "https://reddit.test/old", "posted": "2026-05-01T12:00:00+00:00"},
        ]
        kept = run_mod.filter_rss_records(
            records,
            {"name": "Reddit", "max_age_days": 21},
            datetime(2026, 7, 9, tzinfo=timezone.utc),
        )
        self.assertEqual([row["url"] for row in kept], ["https://reddit.test/good"])

    def test_reddit_group_feed_requires_five_plus_or_group_house(self):
        import run as run_mod
        importlib.reload(run_mod)
        records = [
            {"title": "5BR house for rent in the Mission", "posted": "2026-07-08T12:00:00Z"},
            {"title": "Whole house for rent to a group", "posted": "2026-07-08T12:00:00Z"},
            {"title": "2BR apartment sublet in SOMA", "posted": "2026-07-08T12:00:00Z"},
        ]
        kept = run_mod.filter_rss_records(
            records,
            {"name": "Reddit", "label": "sf-5plus"},
            datetime(2026, 7, 9, tzinfo=timezone.utc),
        )
        self.assertEqual([row["title"] for row in kept], [records[0]["title"], records[1]["title"]])

    def test_run_health_distinguishes_headless_success_and_browser_pending(self):
        import run as run_mod
        importlib.reload(run_mod)
        capture_dir = Path(tempfile.mkdtemp())
        searches = {
            "web": [{"name": "Rent.com", "kind": "rent_next_data", "label": "rent-test", "url": "https://example.test"}],
            "rss": [],
            "apis": [],
            "ai_browser": [{"name": "Zillow Rentals", "label": "zillow-test", "search_url": "https://example.test/zillow"}],
        }
        path = run_mod.expected_capture_paths("web", searches["web"][0], capture_dir)[0]
        path.write_text(json.dumps([{"source": "Rent.com", "title": "Test home", "url": "https://example.test/1"}]))
        start = datetime.now(timezone.utc)
        health = run_mod.build_run_health(
            searches,
            capture_dir,
            start,
            datetime.now(timezone.utc),
            network_enabled=True,
            source_filters={"all"},
            decay_scope="covered",
            pipeline_summary={"created": 1},
        )
        statuses = {row["id"]: row["status"] for row in health["sources"]}
        self.assertEqual(statuses["web:rent-test"], "ok")
        self.assertEqual(statuses["ai_browser:zillow-test"], "pending")
        self.assertEqual(health["overall"], "needs_browser")

    def test_empty_capture_is_not_safe_decay_evidence(self):
        import run as run_mod
        importlib.reload(run_mod)
        capture_dir = Path(tempfile.mkdtemp())
        searches = {
            "web": [{"name": "Rent.com", "kind": "rent_next_data", "label": "rent-test", "url": "https://example.test"}],
            "rss": [], "apis": [], "ai_browser": [],
        }
        started = datetime.now(timezone.utc)
        path = run_mod.expected_capture_paths("web", searches["web"][0], capture_dir)[0]
        path.write_text("[]")
        observed = run_mod.observed_config_sources(
            searches, capture_dir, started, datetime.now(timezone.utc), network_enabled=True,
        )
        self.assertEqual(observed, set())

    def test_partial_source_family_is_not_safe_decay_evidence(self):
        import run as run_mod
        importlib.reload(run_mod)
        capture_dir = Path(tempfile.mkdtemp())
        solo = {"name": "Craigslist", "label": "craigslist-solo", "url": "https://example.test/solo"}
        group = {"name": "Craigslist", "label": "craigslist-sf-5plus", "url": "https://example.test/group"}
        selected = {"web": [solo], "rss": [], "apis": [], "ai_browser": []}
        all_searches = {"web": [solo, group], "rss": [], "apis": [], "ai_browser": []}
        started = datetime.now(timezone.utc)
        path = run_mod.expected_capture_paths("web", solo, capture_dir)[0]
        path.write_text(json.dumps([{"source": "Craigslist", "title": "Room", "url": "https://cl.test/1"}]))
        observed = run_mod.observed_config_sources(
            selected,
            capture_dir,
            started,
            datetime.now(timezone.utc),
            network_enabled=True,
            all_searches=all_searches,
        )
        self.assertEqual(observed, set())

    def test_complete_source_family_can_be_safe_decay_evidence(self):
        import run as run_mod
        importlib.reload(run_mod)
        capture_dir = Path(tempfile.mkdtemp())
        configs = [
            {"name": "Craigslist", "label": "craigslist-solo", "url": "https://example.test/solo"},
            {"name": "Craigslist", "label": "craigslist-sf-5plus", "url": "https://example.test/group"},
        ]
        searches = {"web": configs, "rss": [], "apis": [], "ai_browser": []}
        started = datetime.now(timezone.utc)
        for index, cfg in enumerate(configs):
            path = run_mod.expected_capture_paths("web", cfg, capture_dir)[0]
            path.write_text(json.dumps([{"source": "Craigslist", "title": f"Room {index}", "url": f"https://cl.test/{index}"}]))
        observed = run_mod.observed_config_sources(
            searches,
            capture_dir,
            started,
            datetime.now(timezone.utc),
            network_enabled=True,
            all_searches=searches,
        )
        self.assertEqual(observed, {"Craigslist"})

    def test_run_health_preserves_unselected_source_history(self):
        import run as run_mod
        importlib.reload(run_mod)
        capture_dir = Path(tempfile.mkdtemp())
        selected_cfg = {"name": "Rent.com", "label": "rent-solo", "url": "https://example.test/solo"}
        group_cfg = {"name": "Craigslist", "label": "craigslist-sf-5plus", "url": "https://example.test/group"}
        selected = {"web": [selected_cfg], "rss": [], "apis": [], "ai_browser": []}
        all_searches = {"web": [selected_cfg, group_cfg], "rss": [], "apis": [], "ai_browser": []}
        path = run_mod.expected_capture_paths("web", selected_cfg, capture_dir)[0]
        path.write_text(json.dumps([{"source": "Rent.com", "title": "Unit", "url": "https://rent.test/1"}]))
        prior_success = "2026-07-08T12:00:00+00:00"
        previous = {"sources": [{
            "id": "web:craigslist-sf-5plus", "tier": "web", "name": "Craigslist",
            "label": "craigslist-sf-5plus", "status": "ok", "recordCount": 12,
            "blockedCount": 0, "lastAttemptAt": prior_success, "lastSuccessAt": prior_success,
            "message": "",
        }]}
        started = datetime.now(timezone.utc)
        health = run_mod.build_run_health(
            selected,
            capture_dir,
            started,
            datetime.now(timezone.utc),
            network_enabled=True,
            source_filters={"solo"},
            decay_scope="covered",
            pipeline_summary={},
            previous=previous,
            all_searches=all_searches,
        )
        by_id = {row["id"]: row for row in health["sources"]}
        self.assertFalse(by_id["web:craigslist-sf-5plus"]["selectedThisRun"])
        self.assertEqual(by_id["web:craigslist-sf-5plus"]["lastSuccessAt"], prior_success)
        self.assertEqual(health["summary"]["configured"], 2)
        self.assertEqual(health["summary"]["selectedConfigured"], 1)

    def test_main_partial_run_keeps_full_config_health_manifest(self):
        import run as run_mod
        importlib.reload(run_mod)
        root = Path(tempfile.mkdtemp())
        tracker_dir = root / "trackers"
        health_file = tracker_dir / "run-health.json"
        env = os.environ.copy()
        env.update({
            "HOUSING_TRACKER_DIR": str(tracker_dir),
            "HOUSING_LOCK_FILE": str(root / "pipeline.lock"),
            "HOUSING_CONDUCTOR_LOCK_FILE": str(root / "conductor.lock"),
        })
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "run.py"),
                "--no-network",
                "--fresh-capture-dir",
                "--capture-dir", str(root / "captures"),
                "--sources", "solo",
                "--decay-scope", "none",
                "--health-file", str(health_file),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        health = json.loads(health_file.read_text())
        selected = [row for row in health["sources"] if row.get("selectedThisRun") is not False]
        unselected = [row for row in health["sources"] if row.get("selectedThisRun") is False]
        enabled_total = sum(
            1
            for tier in run_mod.SOURCE_TIERS
            for cfg in run_mod.load_searches().get(tier, [])
            if isinstance(cfg, dict) and cfg.get("enabled", True)
        )
        self.assertTrue(selected)
        self.assertTrue(unselected)
        self.assertEqual(len(health["sources"]), enabled_total)
        self.assertEqual(health["summary"]["selectedConfigured"], len(selected))


if __name__ == "__main__":
    unittest.main()
