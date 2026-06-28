# Housing Preferences

## Anchor

- Office: 2350 Mission College Blvd #750, Santa Clara, CA 95054.
- Work pattern: 3 in-office days per week on Monday, Wednesday, and Thursday (HackerRank RTO). Assume this Mon/Wed/Thu pattern unless Liam says otherwise.
- Start date from offer letter: July 16, 2026.
- Preferred first housing shape: sublease, month-to-month, furnished, or otherwise flexible while learning the Bay Area.
- Open to: San Francisco neighborhoods if Caltrain access makes the commute tolerable; Peninsula/South Bay if value and commute are clearly better.
- Car: possible, but score both no-car and car-enabled scenarios.

## Budget Model

Offer-letter signals used for budget:

- Base salary: $180,000/year.
- Variable component: 10% target.
- Relocation/moving support exists, including one-time relocation allowance and moving expense reimbursement.

Use only base salary for recurring rent. Treat variable compensation as upside and relocation support as one-time help for temporary housing, moving costs, deposit, furniture, and a short overlap period.

Gross monthly base is about $15,000. Housing bands:

| Band | Monthly all-in | Use |
|---|---:|---|
| Room/sublease target | $1,600-$2,800 | Best for flexibility, savings, and testing neighborhoods. |
| Solo sweet spot | $3,000-$3,750 | Strong default for a studio/1BR or premium flexible sublease. |
| Solo stretch | $3,750-$4,500 | Allow only for exceptional commute/location/quality or short-term bridge housing. |
| Overstretch | $4,500+ | Usually reject unless temporary, furnished, and clearly strategic. |

All-in means rent plus recurring mandatory fees, utilities if known, parking if needed, pet fees if applicable, and any monthly service fees.

## Car Scenario

Maintain two scores when possible:

- `No-Car Score`: Caltrain/VTA/walk/bike/rideshare commute; strong for SF near Caltrain, Mountain View, Sunnyvale, Santa Clara, North San Jose transit, and walkable South Bay.
- `Car Score`: drive commute plus parking cost and car ownership burden.

Budget adjustment for car-enabled living:

- Default car burden: $900/month.
- Conservative range: $800-$1,200/month for payment or depreciation, insurance, gas/charging, maintenance, registration, and parking.
- If a listing requires a car to be viable, subtract this burden in scoring unless Liam has confirmed a car purchase and parking plan.

## Commute Targets

Score one-way commute for the 3 in-office days/week (Mon/Wed/Thu), timed to the morning peak Liam would actually travel:

| Door-to-door time | Commute rating |
|---:|---|
| 0-25 min | Excellent |
| 26-40 min | Strong |
| 41-55 min | Good |
| 56-70 min | Tolerable |
| 71-90 min | Weak but possible if train time is productive |
| 90+ min | Usually reject |

Baseline GTFS-derived observations from June 2026 schedules:

- SF Caltrain to Mountain View can be about 46 minutes on express trains before first/last mile.
- SF Caltrain to Sunnyvale can be about 49 minutes on express trains before first/last mile.
- SF Caltrain to Lawrence can be about 58 minutes on limited trains before first/last mile.
- SF Caltrain to Santa Clara can be about 63 minutes on limited trains before first/last mile.
- VTA Orange from Mountain View to Old Ironsides is about 23-25 minutes.
- The office has nearby Mission College/Great America bus stops; last-mile quality matters.

Report both directions: show an expected **to-work (AM)** and **from-work (PM)** door-to-door time. The PM leg runs a little longer (wider off-peak Caltrain headways, more evening traffic); the scorer adds a small PM penalty and the board prints `to work ~Xm / home ~Ym` for both no-car and car.

For San Francisco specifically, Caltrain is the only realistic link to Santa Clara (~63 min train + ~12 min last mile = a fixed ~75 min floor), so what actually separates SF listings is the **first mile to a Caltrain station** (4th & King, or 22nd St). That first mile counts as a **bike** leg, not walk/Muni — Caltrain carries bikes, and biking keeps even "far" SF neighborhoods viable (non-zero but fast). The scorer estimates bike-minutes-to-station per neighborhood: ~4m for Mission Bay/South Beach, ~7-9m for SoMa/Dogpatch/Potrero/Mission, ~13m for Hayes/Castro/Noe/Nob Hill, ~18m for Marina/Richmond/USF/Panhandle, ~25m for Outer Sunset/Richmond. Closer-to-station SF listings should rank above far ones, but all SF stays well behind near-office South Bay because of the fixed ~75 min floor.

Recompute from GTFS/511/Google-style live estimates when making final decisions.

## Markets

Default market buckets:

- San Francisco - Mission/Valencia
- San Francisco - Dogpatch/Potrero/Showplace
- San Francisco - SoMa/South Beach/Mission Bay
- San Francisco - Hayes/Lower Haight/Castro/Duboce
- San Francisco - Sunset/Richmond/Marina/North Beach
- Mountain View
- Sunnyvale
- Santa Clara
- North San Jose
- Palo Alto/Menlo Park
- Redwood City/San Carlos/Belmont
- San Mateo/Burlingame/Millbrae
- Oakland/Berkeley
- Other Bay Area

SF should not be filtered out; it should earn its place through Caltrain access, neighborhood value, and lifestyle upside.
