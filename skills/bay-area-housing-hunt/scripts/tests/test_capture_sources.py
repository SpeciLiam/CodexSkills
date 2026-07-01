import importlib
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
