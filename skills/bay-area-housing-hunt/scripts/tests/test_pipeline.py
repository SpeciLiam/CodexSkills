#!/usr/bin/env python3
"""Regression tests for the housing pipeline — focused on the bugs the review
found. Run: python3 -m unittest discover -s skills/bay-area-housing-hunt/scripts/tests

These tests redirect the trackers to a temp dir via HOUSING_TRACKER_DIR so they
never touch the real housing-trackers/ files."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))


def fresh_module(tmpdir: str):
    os.environ["HOUSING_TRACKER_DIR"] = tmpdir
    import housing_pipeline as hp
    importlib.reload(hp)
    return hp


def base_row(hp, **over):
    row = {c: "" for c in hp.LISTING_COLUMNS}
    row.update({"Status": "Active", "URL": "http://x/1", "Title": "T", "Market": "Santa Clara",
                "Rent": "3000", "All-In Estimate": "3000", "Available": "2026-07-15", "Lease": "sublease"})
    row.update(over)
    return row


class ParseMoney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def test_k_shorthand(self):
        self.assertEqual(self.hp.parse_money("$3.2k"), 3200)
        self.assertEqual(self.hp.parse_money("2.5k"), 2500)
        self.assertEqual(self.hp.parse_money("$2k"), 2000)
        self.assertEqual(self.hp.parse_money("around 3k"), 3000)

    def test_range_takes_high(self):
        self.assertEqual(self.hp.parse_money("$2,800-$3,400"), 3400)

    def test_dollar_anchored_wins(self):
        self.assertEqual(self.hp.parse_money("750 sqft $3200"), 3200)
        self.assertEqual(self.hp.parse_money("2 bed $4200"), 4200)

    def test_junk_rejected(self):
        self.assertEqual(self.hp.parse_money("2 bed available"), 0)
        self.assertEqual(self.hp.parse_money("1 bed 1 bath"), 0)
        self.assertEqual(self.hp.parse_money("studio"), 0)

    def test_plain_number(self):
        self.assertEqual(self.hp.parse_money("3200"), 3200)
        self.assertEqual(self.hp.parse_money("$3,200/mo incl utilities"), 3200)


class StatusLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def test_rejected_is_sticky_on_recapture(self):
        existing = base_row(self.hp, Status="Rejected", Notes="scam risk")
        incoming = self.hp.row_from_record(
            {"title": "T", "url": "http://x/1", "city": "Santa Clara", "rent": "$3,000", "lease": "sublease"},
            "manual", "2026-06-27")
        merged = self.hp.merge_row(existing, incoming, "2026-06-27")
        self.assertEqual(merged["Status"], "Rejected")

    def test_duplicate_is_sticky(self):
        existing = base_row(self.hp, Status="Duplicate")
        incoming = base_row(self.hp, Status="Active")
        merged = self.hp.merge_row(existing, incoming, "2026-06-27")
        self.assertEqual(merged["Status"], "Duplicate")

    def test_expired_can_revive_on_reappear(self):
        existing = base_row(self.hp, Status="Expired")
        incoming = base_row(self.hp, Status="Active")
        merged = self.hp.merge_row(existing, incoming, "2026-06-27")
        self.assertEqual(merged["Status"], "Active")
        self.assertIn("Reappeared", merged["Notes"])

    def test_source_blocked_status_from_capture(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "status": "source blocked", "title": "feed down", "url": "http://cl"},
            "manual", "2026-06-27")
        self.assertEqual(row["Status"], "Source Blocked")

    def test_unavailable_distinct_from_expired(self):
        row = self.hp.row_from_record(
            {"title": "T", "url": "http://x/9", "rent": "$3000", "status": "on hold / pending"},
            "manual", "2026-06-27")
        self.assertEqual(row["Status"], "Unavailable")


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def test_flatten_nested_not_dropped(self):
        wrapper = {"title": "search results page", "results": [
            {"title": "A", "url": "http://a"}, {"title": "B", "url": "http://b"}]}
        recs = self.hp.flatten_records(wrapper)
        self.assertEqual(len(recs), 2)

    def test_listing_key_distinct_on_query(self):
        k1 = self.hp.listing_key("z", "t", "https://site.com/p?listingId=1", "", "", 0)
        k2 = self.hp.listing_key("z", "t", "https://site.com/p?listingId=2", "", "", 0)
        self.assertNotEqual(k1, k2)

    def test_malformed_file_skipped_not_crash(self):
        good = Path(self.tmp) / "good.json"
        bad = Path(self.tmp) / "bad.json"
        good.write_text(json.dumps([{"title": "G", "url": "http://g", "rent": "$3000"}]))
        bad.write_text("{ this is not json ")
        summary = self.hp.run(inputs=[bad, good], default_source="manual", run_date="2026-06-27")
        self.assertEqual(summary["created"], 1)
        self.assertTrue(any("bad.json" in w for w in summary["warnings"]))


class Scoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def _score(self, **over):
        return self.hp.score_row(base_row(self.hp, **over))

    def test_flexible_outranks_rigid_even_worse_commute(self):
        rigid = self._score(Title="1BR", Market="Santa Clara", Lease="12 month lease",
                            Notes="laundry parking", Rent="3200", **{"All-In Estimate": "3200"})
        flex = self._score(Title="Furnished sublease month-to-month", Market="SF Mission/Valencia",
                           Lease="month-to-month sublease furnished", Notes="furnished caltrain",
                           Rent="3200", **{"All-In Estimate": "3200"})
        self.assertGreater(int(flex["Score"]), int(rigid["Score"]))

    def test_unknown_rent_not_above_expensive(self):
        self.assertLess(self.hp.value_score(0), self.hp.value_score(5000))

    def test_why_holds_rationale_notes_stay_clean(self):
        row = self.hp.row_from_record(
            {"title": "Bright room", "url": "http://x/3", "rent": "$2600",
             "lease": "sublease", "description": "Sunny corner unit with balcony"},
            "manual", "2026-06-27")
        self.assertIn("sublease", row["Why"])
        self.assertNotIn("no-car est", row["Notes"])  # rationale must not pollute Notes
        self.assertIn("Sunny corner", row["Notes"])

    def test_terminal_rows_score_zero(self):
        row = self._score(Status="Expired", Notes="Expired 2026-06-28: page deleted")
        self.assertEqual(row["Score"], "0")

    def test_leading_title_price_fallback(self):
        # Craigslist-style: price only in the title, no structured rent field.
        row = self.hp.row_from_record(
            {"source": "Craigslist", "title": "$2,400 / 1br Sunnyvale sublease furnished",
             "url": "http://x/cl1", "lease": "month to month"},
            "Craigslist", "2026-06-27")
        self.assertEqual(row["Rent"], "2400")
        self.assertEqual(row["Status"], "Active")
        # but a title with no $ stays unpriced -> Needs Verification (no invention)
        row2 = self.hp.row_from_record(
            {"source": "Craigslist", "title": "2br near park", "url": "http://x/cl2"},
            "Craigslist", "2026-06-27")
        self.assertEqual(row2["Rent"], "")
        self.assertEqual(row2["Status"], "Needs Verification")


class MarkdownRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def test_backslash_and_pipe_survive(self):
        val = r"unit a | b and C:\path\to"
        decoded = self.hp.split_markdown_row("| " + self.hp.escape_cell(val) + " | next |")[0]
        self.assertEqual(decoded, val)

    def test_marker_injection_does_not_truncate_ledger(self):
        # A listing whose notes contain the literal end-marker must not break the load.
        cap = Path(self.tmp) / "c.json"
        cap.write_text(json.dumps([
            {"title": "A evil " + self.hp.LEDGER_END, "url": "http://x/a", "rent": "$3000",
             "description": "contains " + self.hp.LEDGER_END + " inline"},
            {"title": "B normal", "url": "http://x/b", "rent": "$3100"},
        ]))
        self.hp.run(inputs=[cap], run_date="2026-06-27")
        rows = self.hp.load_listing_rows()
        self.assertEqual(len(rows), 2)  # neither row dropped by a marker inside a cell

    def test_dangling_begin_marker_preserves_prose(self):
        self.hp.run(inputs=[], run_date="2026-06-27", refresh_only=True)
        text = self.hp.LISTINGS_MD.read_text()
        # corrupt: drop the end marker but keep human prose before the begin marker
        corrupted = "# My header\n\nmy notes line\n\n" + text.split(self.hp.LEDGER_END)[0]
        self.hp.LISTINGS_MD.write_text(corrupted)
        self.hp.run(inputs=[], run_date="2026-06-28", refresh_only=True)
        out = self.hp.LISTINGS_MD.read_text()
        self.assertIn("my notes line", out)  # prose before begin survived
        self.assertEqual(out.count(self.hp.LEDGER_BEGIN), 1)  # exactly one clean block
        self.assertEqual(out.count(self.hp.LEDGER_END), 1)

    def test_none_cells_do_not_crash_scoring(self):
        row = {c: None for c in self.hp.LISTING_COLUMNS}
        row["Status"] = "Active"
        self.hp.score_row(row)  # must not raise TypeError on " ".join of None


class CaptureApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)
        import importlib
        import capture_api
        importlib.reload(capture_api)
        self.capture_api = capture_api

    def test_reddit_nested_mapping(self):
        cfg = {
            "name": "Reddit", "source": "Reddit", "list_path": "data.children",
            "id_field": "data.id",
            "field_map": {"title": "data.title", "description": "data.selftext", "url": "data.url"},
        }
        payload = {"data": {"children": [
            {"data": {"id": "x1", "title": "$2,400 room sublease Sunnyvale", "selftext": "m2m", "url": "http://r/x1"}},
            {"data": {"id": "x2", "title": "no url post", "selftext": "y", "url": ""}},
        ]}}
        recs = self.capture_api.map_items(cfg, payload)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["listing_key"], "reddit-x1")
        self.assertEqual(recs[0]["url"], "http://r/x1")

    def test_keyed_api_skipped_without_key(self):
        # An entry with a key_env but no env set must be skipped (no-op), not fetched.
        searches = {"apis": [{"name": "RentCast", "enabled": True, "key_env": "RENTCAST_API_KEY_TEST_MISSING",
                              "url": "https://example.invalid/{city}", "cities": ["X"]}]}
        written = self.capture_api.run_api_capture(Path(self.tmp), searches)
        self.assertEqual(written, [])


class SourceSelection(unittest.TestCase):
    def setUp(self):
        import importlib
        import run as housing_run
        importlib.reload(housing_run)
        self.run = housing_run

    def test_aliases_and_typos_normalize(self):
        filters = self.run.parse_source_filters(["cragislist", "faceb", "apartments.com"])
        self.assertIn("craigslist", filters)
        self.assertIn("facebook", filters)
        self.assertIn("apartments", filters)

    def test_filter_searches_across_tiers(self):
        searches = {
            "web": [
                {"name": "Craigslist", "label": "sf-sublets"},
                {"name": "Zumper", "label": "santa-clara"},
            ],
            "apis": [
                {"name": "Reddit", "source": "Reddit"},
                {"name": "RentCast", "source": "RentCast"},
            ],
            "ai_browser": [
                {"name": "Facebook Marketplace (corridor rentals)"},
                {"name": "Zillow Rentals (corridor)"},
                {"name": "Apartments.com Rentals (corridor)"},
            ],
            "rss": [],
        }
        filtered, filters = self.run.filter_searches(searches, ["craigslist,zillow"])
        self.assertNotIn("all", filters)
        self.assertEqual([x["name"] for x in filtered["web"]], ["Craigslist"])
        self.assertEqual([x["name"] for x in filtered["ai_browser"]], ["Zillow Rentals (corridor)"])
        self.assertEqual(filtered["apis"], [])

    def test_filter_can_select_every_configured_source_family(self):
        searches = {
            "web": [
                {"name": "Craigslist", "label": "south-bay-rooms"},
                {"name": "Zumper", "label": "santa-clara"},
            ],
            "apis": [
                {"name": "Reddit", "source": "Reddit"},
                {"name": "RentCast", "source": "RentCast"},
            ],
            "ai_browser": [
                {"name": "Facebook Marketplace (corridor rentals)"},
                {"name": "Zillow Rentals (corridor)"},
                {"name": "Apartments.com Rentals (corridor)"},
                {"name": "Furnished Finder (Santa Clara area)"},
            ],
            "rss": [],
        }
        filtered, _ = self.run.filter_searches(
            searches,
            ["craigslist", "zumper", "reddit", "rentcast", "facebook", "zillow", "apartments.com", "furnished"],
        )
        self.assertEqual(len(filtered["web"]), 2)
        self.assertEqual(len(filtered["apis"]), 2)
        self.assertEqual(len(filtered["ai_browser"]), 4)

    def test_marketplace_alias_selects_marketplace_not_groups(self):
        searches = {
            "ai_browser": [
                {"name": "Facebook Marketplace (corridor rentals)"},
                {"name": "Facebook housing groups (Bay Area sublets/rooms)"},
            ],
            "web": [],
            "apis": [],
            "rss": [],
        }
        filtered, _ = self.run.filter_searches(searches, ["marketplace"])
        self.assertEqual(
            [item["name"] for item in filtered["ai_browser"]],
            ["Facebook Marketplace (corridor rentals)"],
        )

    def test_five_bedroom_alias_selects_only_sf_5plus_sources(self):
        searches = {
            "web": [
                {"name": "Craigslist", "label": "sf-apartments"},
                {"name": "Craigslist", "label": "sf-apartments-5plus"},
                {"name": "Craigslist", "label": "sf-sublets-5plus"},
                {"name": "Zumper", "label": "zumper-sf-5plus"},
                {"name": "Craigslist", "label": "south-bay-apartments"},
            ],
            "apis": [],
            "ai_browser": [
                {"name": "Facebook Marketplace (SF 5+ bedroom rentals)", "label": "facebook-sf-5plus"},
                {"name": "Zillow Rentals (SF 5+ bedrooms)", "label": "zillow-sf-5plus"},
                {"name": "Apartments.com Rentals (SF 5+ bedrooms)", "label": "apartments-com-sf-5plus"},
                {"name": "Zillow Rentals (corridor)"},
            ],
            "rss": [],
        }
        filtered, _ = self.run.filter_searches(searches, ["5br"])
        self.assertEqual(
            [item["label"] for item in filtered["web"]],
            ["sf-apartments-5plus", "sf-sublets-5plus", "zumper-sf-5plus"],
        )
        self.assertEqual(
            [item["label"] for item in filtered["ai_browser"]],
            ["facebook-sf-5plus", "zillow-sf-5plus", "apartments-com-sf-5plus"],
        )

    def test_capture_dir_glob_respects_source_filter(self):
        filters = self.run.parse_source_filters(["zillow"])
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/ai-zillow-rentals-corridor.json"), filters))
        self.assertFalse(self.run.capture_path_matches(Path("/tmp/web-craigslist-sf-sublets.json"), filters))

    def test_capture_dir_glob_respects_five_bedroom_filter(self):
        filters = self.run.parse_source_filters(["5br"])
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/web-Zumper-zumper-sf-5plus.json"), filters))
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/ai-zillow-sf-5plus.json"), filters))
        self.assertFalse(self.run.capture_path_matches(Path("/tmp/ai-zillow-rentals-corridor.json"), filters))

    def test_all_keeps_everything(self):
        searches = {"web": [{"name": "Craigslist"}], "apis": [{"name": "Reddit"}], "ai_browser": [], "rss": []}
        filtered, filters = self.run.filter_searches(searches, ["all"])
        self.assertIn("all", filters)
        self.assertEqual(filtered, searches)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hp = fresh_module(self.tmp)

    def test_full_run_and_human_prose_preserved(self):
        cap = Path(self.tmp) / "cap.json"
        cap.write_text(json.dumps([
            {"title": "Furnished Mission sublease near 22nd St Caltrain", "url": "http://x/m1",
             "city": "San Francisco", "neighborhood": "Mission", "rent": "$3.2k",
             "lease": "month-to-month furnished", "available": "2026-07-15"},
            {"title": "Santa Clara 1BR", "url": "http://x/sc1", "city": "Santa Clara",
             "rent": "$3300", "lease": "12 month", "available": "2026-08-01"},
        ]))
        s1 = self.hp.run(inputs=[cap], default_source="manual", run_date="2026-06-27")
        self.assertEqual(s1["created"], 2)
        # the $3.2k listing must be parsed as 3200, not 3
        listings = Path(s1["listings"]).read_text()
        self.assertIn("3200", listings)
        self.assertNotIn("| 3 |", listings)
        # add human prose outside the managed block; a re-run must preserve it
        text = Path(s1["listings"]).read_text()
        Path(s1["listings"]).write_text(text + "\n\n## My shortlist notes\n- call the Mission one\n")
        s2 = self.hp.run(inputs=[], default_source="manual", run_date="2026-06-28", refresh_only=True)
        self.assertIn("My shortlist notes", Path(s2["listings"]).read_text())


if __name__ == "__main__":
    unittest.main()
