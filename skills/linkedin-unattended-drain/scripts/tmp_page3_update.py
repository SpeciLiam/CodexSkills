import json
from datetime import datetime, timezone

p = '/tmp/linkedin_unattended_drain_state.json'
s = json.load(open(p))
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

visited_new = [
    'https://www.linkedin.com/jobs/view/4426565589/',
    'https://www.linkedin.com/jobs/view/4426554169/',
    'https://www.linkedin.com/jobs/view/4422766604/',
    'https://www.linkedin.com/jobs/view/4426525402/',
    'https://www.linkedin.com/jobs/view/4425890391/',
    'https://www.linkedin.com/jobs/view/4426506959/',
    'https://www.linkedin.com/jobs/view/4426398915/',
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

page3_items = [
    {'key': 'linkedin-4426565589', 'state': 'archived', 'company': 'Capgemini',
     'role': 'Java springboot developer - Senior Software Engineer', 'location': 'Berwyn IL (Hybrid)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426565589/',
     'postingKey': 'linkedin-4426565589',
     'result': 'Archived: IT consulting/staffing firm. IL hybrid. Senior-level framing mismatch.',
     'updatedAt': now},
    {'key': 'linkedin-4426554169', 'state': 'archived', 'company': 'Northrop Grumman',
     'role': '2027 Associate Software Engineer/Software Engineer', 'location': 'Emerado ND (On-site)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426554169/',
     'postingKey': 'linkedin-4426554169',
     'result': 'Archived: defense contractor, clearance required. ND on-site geo mismatch.',
     'updatedAt': now},
    {'key': 'linkedin-4422766604', 'state': 'duplicate', 'company': 'BeaconFire Inc.',
     'role': 'Java Software Engineer', 'location': 'New York NY (Hybrid)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4422766604/',
     'postingKey': 'linkedin-4422766604',
     'result': 'Duplicate: BeaconFire repost. Already applied 2026-05-29.',
     'updatedAt': now},
    {'key': 'linkedin-4426525402', 'state': 'archived', 'company': 'SS&C Technologies',
     'role': 'Software Development Engineer in Test', 'location': 'San Francisco CA (Hybrid)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426525402/',
     'postingKey': 'linkedin-4426525402',
     'result': 'Archived: SDET/QA engineering role, not SWE target. Already archived this company+role type.',
     'updatedAt': now},
    {'key': 'linkedin-4425890391', 'state': 'archived', 'company': 'Excellerate Education Solutions',
     'role': 'Software Developers', 'location': 'Palatine IL (On-site)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4425890391/',
     'postingKey': 'linkedin-4425890391',
     'result': 'Archived: IL on-site, geo mismatch. Small education solutions firm, no JD detail captured.',
     'updatedAt': now},
    {'key': 'linkedin-4426506959', 'state': 'tailor_needed',
     'company': 'Valerie Health', 'role': 'Software Engineer - Product',
     'location': 'San Francisco CA (On-site)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426506959/',
     'postingKey': 'linkedin-4426506959',
     'jobDescriptionPath': '/tmp/linkedin_unattended_drain_descriptions/linkedin-4426506959.txt',
     'result': 'AI/ML healthcare startup (Stripe/Uber alumni). LLM workflows, computer-use, vision models. Product eng hybrid PM/Eng role. SF on-site.',
     'updatedAt': now},
    {'key': 'linkedin-4426398915', 'state': 'archived', 'company': 'Doppel',
     'role': 'Forward Deployed Engineer', 'location': 'Utica-Rome Area (Hybrid)',
     'jobUrl': 'https://www.linkedin.com/jobs/view/4426398915/',
     'postingKey': 'linkedin-4426398915',
     'result': 'Archived: enterprise onboarding/integrations/project-mgmt role (not core SWE). Different from Infrastructure role applied today. Utica NY not preferred location.',
     'updatedAt': now},
]

for item in page3_items:
    upsert(item)

s['search']['lastJobUrl'] = 'https://www.linkedin.com/jobs/view/4426398915/'
s['search']['currentResultIndex'] = 50 + 7
s['updatedAt'] = now
json.dump(s, open(p, 'w'), indent=2)

terminal = sum(1 for i in s['items'] if i['state'] in ['submitted', 'manual', 'duplicate', 'archived', 'already_applied', 'already_submitted'])
tailor = [i['company'] for i in s['items'] if i['state'] == 'tailor_needed']
print('terminal:', terminal, '/ 20, tailor_needed:', tailor)
print('visitedUrls:', len(s['search']['visitedJobUrls']))
