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
from datetime import datetime, timedelta, timezone
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

    def test_sf_bucket_spillover_reclassified_by_explicit_city(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "SF SoMa/South Beach/Mission Bay",
             "city": "Oakland", "title": "Sunny Spacious Room Sublet", "url": "http://x/oak",
             "rent": "$870"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "Oakland/Berkeley")

    def test_sf_bucket_out_of_area_spillover_not_counted_as_sf(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "SF SoMa/South Beach/Mission Bay",
             "city": "San Luis Obispo", "title": "House to sublease", "url": "http://x/slo",
             "rent": "$1430"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "Other Bay Area")

    def test_sf_neighborhood_stays_in_sf_bucket(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "SF SoMa/South Beach/Mission Bay",
             "city": "Mission District", "title": "Furnished Mission sublease", "url": "http://x/sf",
             "rent": "$3200"},
            "Craigslist", "2026-07-01")
        self.assertTrue(row["Market"].startswith("SF "))

    def test_non_sf_bucket_spillover_reclassified_by_explicit_city(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "Santa Clara",
             "city": "Oakland", "title": "One bedroom for sublet", "url": "http://x/oak2",
             "rent": "$597"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "Oakland/Berkeley")

    def test_south_bay_out_of_area_spillover_not_counted_as_santa_clara(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "Santa Clara",
             "city": "Santa Cruz Pleasure Point", "title": "Ocean escape", "url": "http://x/scz",
             "rent": "$3500"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "Other Bay Area")

    def test_geo_first_market_bucket_overrides_bad_hint(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "Santa Clara", "city": "San Francisco",
             "neighborhood": "Castro", "title": "Castro furnished room",
             "url": "http://x/castro", "rent": "$2400", "lat": "37.7609", "lng": "-122.4350"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "SF Hayes/Lower Haight/Castro/Duboce")

    def test_slug_city_spillover_is_other_bay_area(self):
        row = self.hp.row_from_record(
            {"source": "Craigslist", "market": "Santa Clara", "city": "",
             "title": "santa-cruz-1100-month ocean room", "url": "https://sfbay.craigslist.org/sby/roo/d/santa-cruz-1100-month/1.html",
             "rent": "$1100"},
            "Craigslist", "2026-07-01")
        self.assertEqual(row["Market"], "Other Bay Area")
        self.assertIn("location out of search area", row["Notes"])

    def test_nob_hill_and_usf_neighborhoods_are_sf_bucketed(self):
        nob = self.hp.row_from_record(
            {"source": "Craigslist", "market": "SF Sunset/Richmond/Marina/North Beach",
             "city": "San Francisco", "title": "Fully Furnished Nob hill 1BR/1BA Sublet w/ Home Office",
             "url": "http://x/nob", "rent": "$3000"},
            "Craigslist", "2026-07-01")
        usf = self.hp.row_from_record(
            {"source": "Craigslist", "market": "SF SoMa/South Beach/Mission Bay",
             "city": "San Francisco", "title": "USF Panhandle furnished room",
             "url": "http://x/usf", "rent": "$2100"},
            "Craigslist", "2026-07-01")
        self.assertEqual(nob["Market"], "SF Sunset/Richmond/Marina/North Beach")
        self.assertEqual(usf["Market"], "SF Sunset/Richmond/Marina/North Beach")

    def test_bare_sf_neighborhood_words_do_not_override_non_sf_locations(self):
        richmond = self.hp.reconcile_market(
            "", "Richmond", "", "Room for rent in Richmond near BART", "")
        fremont = self.hp.reconcile_market(
            "", "Fremont", "", "Room in Mission San Jose", "")
        mission_college = self.hp.row_from_record(
            {"source": "Craigslist", "city": "Santa Clara",
             "title": "Room near Mission College", "url": "http://x/mission-college",
             "rent": "$1800"},
            "Craigslist", "2026-07-01")
        self.assertNotEqual(richmond, "SF Sunset/Richmond/Marina/North Beach")
        self.assertNotEqual(fremont, "SF Mission/Valencia")
        self.assertEqual(mission_college["Market"], "Santa Clara")

    def test_sf_neighborhood_words_require_sf_context(self):
        market = self.hp.reconcile_market(
            "", "San Francisco", "", "Room in the Mission near Valencia", "")
        cl_market = self.hp.reconcile_market(
            "", "", "", "Room in the Richmond", "", url="https://sfbay.craigslist.org/sfc/roo/d/x/1.html")
        self.assertEqual(market, "SF Mission/Valencia")
        self.assertEqual(cl_market, "SF Sunset/Richmond/Marina/North Beach")

    def test_weekly_and_short_term_rents_are_normalized(self):
        weekly = self.hp.row_from_record(
            {"source": "Craigslist", "title": "Modern1 bedroom state-of-the-art residence $400 Weekly",
             "url": "http://x/weekly", "city": "San Francisco", "rent": "$400"},
            "Craigslist", "2026-07-01")
        short = self.hp.row_from_record(
            {"source": "Craigslist", "title": "Furnished 1BR/1BA sublet June 30-July 15, $1495",
             "url": "http://x/short", "city": "San Francisco", "rent": "$1495"},
            "Craigslist", "2026-07-01")
        self.assertEqual(weekly["Rent"], "1732")
        self.assertIn("raw rent $400/wk normalized", weekly["Notes"])
        self.assertEqual(short["Rent"], "2990")
        self.assertIn("total-for-term normalized", short["Notes"])

    def test_same_source_repost_marks_older_duplicate_and_preserves_first_seen(self):
        cap1 = Path(self.tmp) / "cap1.json"
        cap2 = Path(self.tmp) / "cap2.json"
        cap1.write_text(json.dumps([
            {"source": "Craigslist", "listing_key": "craigslist-7943383373",
             "title": "Fully Furnished Nob hill 1BR/1BA Sublet w/ Home Office",
             "url": "http://x/old", "city": "San Francisco", "rent": "$3000", "beds": "1 bd"}
        ]))
        cap2.write_text(json.dumps([
            {"source": "Craigslist", "listing_key": "craigslist-7944267649",
             "title": "Fully Furnished Nob hill 1BR/1BA Sublet w/ Home Office",
             "url": "http://x/new", "city": "San Francisco", "rent": "$3000", "beds": "1 bd"}
        ]))
        self.hp.run(inputs=[cap1], default_source="Craigslist", run_date="2026-06-30")
        self.hp.run(inputs=[cap2], default_source="Craigslist", run_date="2026-07-01")
        rows = {row["Listing Key"]: row for row in self.hp.load_listing_rows()}
        self.assertEqual(rows["craigslist-7943383373"]["Status"], "Duplicate")
        self.assertEqual(rows["craigslist-7944267649"]["Status"], "Active")
        self.assertEqual(rows["craigslist-7944267649"]["First Seen"], "2026-06-30")

    def test_scam_median_and_repeated_cluster_flag_needs_verification(self):
        cap = Path(self.tmp) / "scams.json"
        cap.write_text(json.dumps([
            {"source": "Craigslist", "title": "Normal Santa Clara 1BR A", "url": "http://x/a", "city": "Santa Clara", "rent": "$3000", "beds": "1 bd"},
            {"source": "Craigslist", "title": "Normal Santa Clara 1BR B", "url": "http://x/b", "city": "Santa Clara", "rent": "$3200", "beds": "1 bd"},
            {"source": "Craigslist", "title": "Modern1 bedroom state-of-the-art residence $400 Weekly", "url": "http://x/c", "city": "Santa Clara", "rent": "$400", "beds": "1 bd"},
            {"source": "Craigslist", "title": "LRG RM near campus one", "url": "http://x/d", "city": "Santa Clara", "rent": "$2198"},
            {"source": "Craigslist", "title": "LRG RM near campus two", "url": "http://x/e", "city": "Santa Clara", "rent": "$2198"},
            {"source": "Craigslist", "title": "LRG RM near campus three", "url": "http://x/f", "city": "Santa Clara", "rent": "$2198"},
        ]))
        self.hp.run(inputs=[cap], default_source="Craigslist", run_date="2026-07-01")
        rows = self.hp.load_listing_rows()
        weekly = next(row for row in rows if "Weekly" in row["Title"])
        cluster = [row for row in rows if row["Title"].startswith("LRG RM")]
        self.assertEqual(weekly["Status"], "Needs Verification")
        self.assertIn("scam-risk", weekly["Notes"])
        self.assertTrue(all(row["Status"] == "Needs Verification" for row in cluster))

    def test_term_fit_gate_excludes_short_window_from_overall(self):
        cap = Path(self.tmp) / "terms.json"
        cap.write_text(json.dumps([
            {"title": "Furnished 1BR/1BA sublet June 30-July 15, $1495",
             "url": "http://x/short-term", "city": "Santa Clara", "rent": "$1495", "lease": "sublet"},
            {"title": "Good Santa Clara sublease July 16-Sep 30",
             "url": "http://x/good", "city": "Santa Clara", "rent": "$2200", "lease": "sublet"},
        ]))
        summary = self.hp.run(inputs=[cap], default_source="manual", run_date="2026-07-01")
        rows = self.hp.load_listing_rows()
        short = next(row for row in rows if "June 30" in row["Title"])
        rankings = Path(summary["rankings"]).read_text()
        overall = rankings.split("## Top 5 Overall Active", 1)[1].split("## Top 5 By Market", 1)[0]
        self.assertIn("term ends 2026-07-15", short["Notes"])
        self.assertNotIn("June 30-July 15", overall)


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

    def test_sf_first_mile_uses_coordinates_when_available(self):
        bike, note = self.hp.sf_no_car_first_mile("Outer Richmond", "far from Caltrain", "37.7577", "-122.3925")
        self.assertLessEqual(bike, 4)
        self.assertIn("22nd St", note)


class CommuteExports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        fresh_module(self.tmp)
        import commute_origins
        import export_housing_data
        importlib.reload(commute_origins)
        importlib.reload(export_housing_data)
        self.co = commute_origins
        self.exporter = export_housing_data

    def test_origin_key_prefers_rounded_coordinates_with_address_fallback(self):
        geo = self.co.origin_key("Santa Clara", "Santa Clara", "", "37.35324", "-121.93674")
        fallback = self.co.origin_key("Santa Clara", "Santa Clara", "")
        self.assertEqual(geo, "geo:37.353,-121.937")
        self.assertEqual(fallback, "santa clara, ca")

    def test_google_cache_lookup_falls_back_to_legacy_address_key(self):
        listing = {
            "market": "Santa Clara",
            "city": "Santa Clara",
            "neighborhood": "",
            "lat": 37.35324,
            "lng": -121.93674,
            "officeCommutes": self.exporter.office_commutes("Santa Clara"),
        }
        fallback_key = self.co.origin_key("Santa Clara", "Santa Clara", "")
        cache = {fallback_key: {
            "office": {self.co.PRIMARY_OFFICE: {"transit": 12, "drive": 8, "transitSummary": "Caltrain"}},
            "homeTransit": 14,
        }}
        self.assertTrue(self.exporter.apply_google_commute(listing, cache))
        self.assertEqual(listing["commuteSource"], "google")
        self.assertEqual(listing["commuteMin"], 12)

    def test_geo_estimate_source_when_coordinates_exist_without_google(self):
        listing = {"lat": 37.35324, "lng": -121.93674}
        listing.setdefault("commuteSource", "geo-estimate" if self.exporter.has_coords(listing) else "region-default")
        self.assertEqual(listing["commuteSource"], "geo-estimate")


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

    def test_web_capture_extracts_cl_and_zumper_coordinates(self):
        import capture_web
        importlib.reload(capture_web)
        cl_payload = {"data": {
            "decode": {"minPostingId": 7940000000, "locationDescriptions": ["", "San Francisco"]},
            "location": {"url": "sfbay.craigslist.org"},
            "params": {"subarea": "sfc"},
            "categoryAbbr": "sub",
            "items": [[3383373, "abc", "Fully Furnished Nob hill 1BR/1BA Sublet", 3000, "0:1~37.7930~-122.4160", [6, "nob-hill-sublet"]]],
        }}
        cl = capture_web.parse_craigslist(cl_payload, {"name": "Craigslist", "subarea": "sfc", "category": "sub"})
        self.assertEqual(cl[0]["lat"], "37.7930")
        self.assertEqual(cl[0]["lng"], "-122.4160")
        state = {"currentSearch": {"listables": {"listables": [
            {"listing_id": "z1", "min_price": 3100, "max_price": 3100, "city": "Santa Clara",
             "geo": {"latitude": 37.355, "longitude": -121.995}}
        ]}}}
        z = capture_web.parse_zumper(state, {"market_hint": "Santa Clara"})
        self.assertEqual(z[0]["lat"], "37.355")
        self.assertEqual(z[0]["lng"], "-121.995")


class SourceSelection(unittest.TestCase):
    def setUp(self):
        import importlib
        import run as housing_run
        importlib.reload(housing_run)
        self.run = housing_run

    def _enabled_source_keys(self, searches):
        keys = set()
        for tier in self.run.SOURCE_TIERS:
            for cfg in searches.get(tier, []):
                if isinstance(cfg, dict) and cfg.get("enabled", True):
                    keys.add(self._source_key(tier, cfg))
        return keys

    def _source_keys(self, searches):
        keys = set()
        for tier in self.run.SOURCE_TIERS:
            for cfg in searches.get(tier, []):
                if isinstance(cfg, dict) and cfg.get("enabled", True):
                    keys.add(self._source_key(tier, cfg))
        return keys

    def _source_key(self, tier, cfg):
        return (
            tier,
            cfg.get("label", ""),
            cfg.get("name", ""),
            cfg.get("source", ""),
            cfg.get("search_url") or cfg.get("url", ""),
        )

    def test_aliases_and_typos_normalize(self):
        filters = self.run.parse_source_filters(["cragislist", "faceb", "apartments.com"])
        self.assertIn("craigslist", filters)
        self.assertIn("facebook", filters)
        self.assertIn("apartments", filters)
        self.assertEqual(self.run.parse_source_filters(["liam"]), {"solo"})
        self.assertEqual(self.run.parse_source_filters(["group"]), {"sf5plus"})

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
                {"name": "Craigslist", "label": "south-bay-apartments-5plus"},
                {"name": "Zumper", "label": "zumper-sf-5plus"},
                {"name": "Zumper", "label": "zumper-santa-clara-5plus"},
                {"name": "Craigslist", "label": "south-bay-apartments"},
            ],
            "apis": [],
            "ai_browser": [
                {"name": "Facebook Marketplace (SF 5+ bedroom rentals)", "label": "facebook-sf-5plus"},
                {"name": "Zillow Rentals (South Bay 5+ bedrooms)", "label": "zillow-south-bay-5plus"},
                {"name": "Zillow Rentals (SF 5+ bedrooms)", "label": "zillow-sf-5plus"},
                {"name": "Apartments.com Rentals (SF 5+ bedrooms)", "label": "apartments-com-sf-5plus"},
                {"name": "Apartments.com Rentals (Peninsula 5+ bedrooms)", "label": "apartments-com-peninsula-5plus"},
                {"name": "Zillow Rentals (corridor)"},
            ],
            "rss": [],
        }
        filtered, _ = self.run.filter_searches(searches, ["5br"])
        self.assertEqual(
            [item["label"] for item in filtered["web"]],
            ["sf-apartments-5plus", "sf-sublets-5plus", "south-bay-apartments-5plus", "zumper-sf-5plus", "zumper-santa-clara-5plus"],
        )
        self.assertEqual(
            [item["label"] for item in filtered["ai_browser"]],
            ["facebook-sf-5plus", "zillow-south-bay-5plus", "zillow-sf-5plus", "apartments-com-sf-5plus", "apartments-com-peninsula-5plus"],
        )

    def test_sf_five_plus_alias_stays_sf_only(self):
        searches = {
            "web": [
                {"name": "Craigslist", "label": "sf-apartments-5plus"},
                {"name": "Craigslist", "label": "south-bay-apartments-5plus"},
            ],
            "apis": [],
            "ai_browser": [
                {"name": "Zillow Rentals (SF 5+ bedrooms)", "label": "zillow-sf-5plus"},
                {"name": "Zillow Rentals (Peninsula 5+ bedrooms)", "label": "zillow-peninsula-5plus"},
            ],
            "rss": [],
        }
        filtered, _ = self.run.filter_searches(searches, ["sf5plus"])
        self.assertEqual([item["label"] for item in filtered["web"]], ["sf-apartments-5plus"])
        self.assertEqual([item["label"] for item in filtered["ai_browser"]], ["zillow-sf-5plus"])

    def test_solo_excludes_five_plus_lanes_and_keeps_normal_lanes(self):
        searches = self.run.load_searches()
        filtered, _ = self.run.filter_searches(searches, ["solo"])
        selected = self._source_keys(filtered)
        self.assertTrue(selected)
        for tier in self.run.SOURCE_TIERS:
            for cfg in filtered.get(tier, []):
                label = str(cfg.get("label", "")).lower()
                self.assertNotIn("5plus", label)
        normal_enabled = [
            self._source_key(tier, cfg)
            for tier in self.run.SOURCE_TIERS
            for cfg in searches.get(tier, [])
            if isinstance(cfg, dict)
            and cfg.get("enabled", True)
            and "5plus" not in str(cfg.get("label", "")).lower()
        ]
        self.assertTrue(normal_enabled)
        self.assertTrue(set(normal_enabled).issubset(selected))

    def test_group_alias_matches_sf_five_plus(self):
        searches = self.run.load_searches()
        group, _ = self.run.filter_searches(searches, ["group"])
        sf5plus, _ = self.run.filter_searches(searches, ["sf5plus"])
        self.assertEqual(self._source_keys(group), self._source_keys(sf5plus))

    def test_solo_and_group_partition_enabled_lanes(self):
        searches = self.run.load_searches()
        solo, _ = self.run.filter_searches(searches, ["solo"])
        group, _ = self.run.filter_searches(searches, ["group"])
        solo_keys = self._source_keys(solo)
        group_keys = self._source_keys(group)
        self.assertEqual(solo_keys & group_keys, set())
        self.assertEqual(solo_keys | group_keys, self._enabled_source_keys(searches))

    def test_capture_dir_glob_respects_source_filter(self):
        filters = self.run.parse_source_filters(["zillow"])
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/ai-zillow-rentals-corridor.json"), filters))
        self.assertFalse(self.run.capture_path_matches(Path("/tmp/web-craigslist-sf-sublets.json"), filters))

    def test_capture_dir_glob_respects_five_bedroom_filter(self):
        filters = self.run.parse_source_filters(["5br"])
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/web-Zumper-zumper-sf-5plus.json"), filters))
        self.assertTrue(self.run.capture_path_matches(Path("/tmp/ai-zillow-sf-5plus.json"), filters))
        self.assertFalse(self.run.capture_path_matches(Path("/tmp/ai-zillow-rentals-corridor.json"), filters))

    def test_stale_ai_capture_skipped_unless_explicit(self):
        p = Path(tempfile.mkdtemp()) / "ai-zillow-sf-5plus.json"
        p.write_text("[]")
        now = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
        stale_mtime = (now - timedelta(hours=24)).timestamp()
        os.utime(p, (stale_mtime, stale_mtime))
        warning = self.run.stale_ai_capture_warning(p, set(), False, now)
        self.assertIn("skipped stale AI capture", warning)
        self.assertIsNone(self.run.stale_ai_capture_warning(p, {p.resolve()}, False, now))
        self.assertIsNone(self.run.stale_ai_capture_warning(p, set(), True, now))

    def test_fresh_ai_capture_allowed_from_capture_dir(self):
        p = Path(tempfile.mkdtemp()) / "ai-apartments-com-sf-5plus.json"
        p.write_text("[]")
        now = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
        fresh_mtime = (now - timedelta(hours=2)).timestamp()
        os.utime(p, (fresh_mtime, fresh_mtime))
        self.assertIsNone(self.run.stale_ai_capture_warning(p, set(), False, now))

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
