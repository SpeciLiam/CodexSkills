import json
from datetime import datetime, timezone

p = '/tmp/linkedin_unattended_drain_state.json'
s = json.load(open(p))
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

visited_new = [
    'https://www.linkedin.com/jobs/view/4426570086/',
    'https://www.linkedin.com/jobs/view/4421996520/',
    'https://www.linkedin.com/jobs/view/4426542010/',
    'https://www.linkedin.com/jobs/view/4426541015/',
    'https://www.linkedin.com/jobs/view/4426532379/',
    'https://www.linkedin.com/jobs/view/4426530364/',
    'https://www.linkedin.com/jobs/view/4426532385/',
]
for u in visited_new:
    if u not in s['search']['visitedJobUrls']:
        s['search']['visitedJobUrls'].append(u)

def upsert(item):
    for i, it in enumerate(s['items']):
        if it['key'] == item['key']:
            s['items'][i] = item
            return
    s['items'].append(item)

page2_items = [
    {'key': 'linkedin-4426570086', 'state': 'archived', 'company': 'Northrop Grumman',
     'role': '2027 Associate Software Engineer/Software Engineer', 'location': 'El Segundo CA',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426570086/',
     'postingKey': 'linkedin-4426570086',
     'result': 'Archived: defense contractor, requires clearance/citizenship verification. Domain mismatch.',
     'updatedAt': now},
    {'key': 'linkedin-4421996520', 'state': 'duplicate', 'company': 'BeaconFire Inc.',
     'role': 'Java Software Engineer', 'location': 'East Windsor NJ',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4421996520/',
     'postingKey': 'linkedin-4421996520',
     'result': 'Duplicate: BeaconFire repost. Already applied to BeaconFire Software Engineer Entry Level (4417989141) 2026-05-29.',
     'updatedAt': now},
    {'key': 'linkedin-4426542010', 'state': 'archived', 'company': 'Akraya, Inc.',
     'role': 'Software Dev Engineer II: 26-01634', 'location': 'Bellevue WA',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426542010/',
     'postingKey': 'linkedin-4426542010',
     'result': 'Archived: Contract type explicitly shown in LinkedIn header. Liam seeking full-time only.',
     'updatedAt': now},
    {'key': 'linkedin-4426541015', 'state': 'archived', 'company': 'Broward Health',
     'role': 'AI Software Developer - Associate-IT-BHC', 'location': 'Fort Lauderdale FL (on-site)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426541015/',
     'postingKey': 'linkedin-4426541015',
     'result': 'Archived: Fort Lauderdale FL on-site only. Geo mismatch (Liam in Seattle).',
     'updatedAt': now},
    {'key': 'linkedin-4426532379', 'state': 'archived', 'company': 'General Dynamics Information Technology',
     'role': 'Software Developer', 'location': 'United States (Remote)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426532379/',
     'postingKey': 'linkedin-4426532379',
     'result': 'Archived: GDIT is a defense IT contractor; most roles require government clearance. Responses managed off LinkedIn — could not load JD to verify.',
     'updatedAt': now},
    {'key': 'linkedin-4426530364', 'state': 'archived', 'company': 'SS&C Technologies',
     'role': 'Software Development Engineer in Test', 'location': 'Boston MA (Hybrid)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426530364/',
     'postingKey': 'linkedin-4426530364',
     'result': 'Archived: SDET/QA engineering role (not SWE target). Boston MA hybrid — geo mismatch for Seattle-based Liam.',
     'updatedAt': now},
    {'key': 'linkedin-4426532385', 'state': 'archived', 'company': 'Lockheed Martin',
     'role': 'Software Engineer- GUI Development', 'location': 'Bothell WA (On-site)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426532385/',
     'postingKey': 'linkedin-4426532385',
     'result': 'Archived: defense contractor, requires clearance. GUI development specialty mismatch.',
     'updatedAt': now},
]

for item in page2_items:
    upsert(item)

s['search']['lastJobUrl'] = 'https://www.linkedin.com/jobs/view/4426532385/'
s['search']['currentResultIndex'] = 25 + 7
s['updatedAt'] = now
json.dump(s, open(p, 'w'), indent=2)

terminal = sum(1 for i in s['items'] if i['state'] in ['submitted', 'manual', 'duplicate', 'archived', 'already_applied', 'already_submitted'])
tailor = [i['company'] for i in s['items'] if i['state'] == 'tailor_needed']
print('terminal:', terminal, '/ 20, tailor_needed:', tailor)
print('visitedUrls:', len(s['search']['visitedJobUrls']))
