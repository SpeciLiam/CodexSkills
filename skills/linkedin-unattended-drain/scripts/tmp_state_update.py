import json
from datetime import datetime, timezone

p = '/tmp/linkedin_unattended_drain_state.json'
s = json.load(open(p))
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

visited_new = [
    'https://www.linkedin.com/jobs/view/4422747869/',
    'https://www.linkedin.com/jobs/view/4426560536/',
    'https://www.linkedin.com/jobs/view/4426546692/',
    'https://www.linkedin.com/jobs/view/4422750879/',
    'https://www.linkedin.com/jobs/view/4426009155/',
    'https://www.linkedin.com/jobs/view/4422758824/',
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

new_items = [
    {
        'key': 'linkedin-4422747869', 'state': 'archived',
        'company': 'Leonardo DRS', 'role': 'Software Engineer II', 'location': 'US',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4422747869/',
        'postingKey': 'linkedin-4422747869',
        'result': 'Archived: reliability/FMEA/defense engineering, not SWE. Active DOD clearance required. Domain mismatch.',
        'updatedAt': now
    },
    {
        'key': 'linkedin-4426560536', 'state': 'archived',
        'company': 'TekWissen India', 'role': 'Software Developer', 'location': 'Remote',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4426560536/',
        'postingKey': 'linkedin-4426560536',
        'result': 'Archived: 9-month contract via staffing agency. Liam seeking full-time only.',
        'updatedAt': now
    },
    {
        'key': 'linkedin-4426546692', 'state': 'tailor_needed',
        'company': 'DND Solutions', 'role': 'Full-stack Developer', 'location': 'United States (Remote)',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4426546692/',
        'postingKey': 'linkedin-4426546692',
        'jobDescriptionPath': '/tmp/linkedin_unattended_drain_descriptions/linkedin-4426546692.txt',
        'result': 'Fresh remote full-stack. Matches React/NestJS/Node/TS background.',
        'updatedAt': now
    },
    {
        'key': 'linkedin-4422750879', 'state': 'archived',
        'company': 'fieldd', 'role': 'Software Engineer', 'location': 'Austin TX (in-person)',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4422750879/',
        'postingKey': 'linkedin-4422750879',
        'result': 'Archived: Austin in-person mandatory (posting says do not apply if not in Austin). Liam is in Seattle.',
        'updatedAt': now
    },
    {
        'key': 'linkedin-4426009155', 'state': 'tailor_needed',
        'company': 'OpenAI', 'role': 'Software Engineer Internal Applications Enterprise',
        'location': 'San Francisco CA or fully remote',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4426009155/',
        'postingKey': 'linkedin-4426009155',
        'jobDescriptionPath': '/tmp/linkedin_unattended_drain_descriptions/linkedin-4426009155.txt',
        'result': 'Net-new OpenAI role (not in tracker). Full-stack ITSM/agentic internal tooling. $293-342K. SF/remote.',
        'updatedAt': now
    },
    {
        'key': 'linkedin-4422758824', 'state': 'archived',
        'company': 'Bosch USA',
        'role': 'Rotational Development Program Software Engineer Power Solutions',
        'location': 'Multiple US sites',
        'jobUrl': 'https://www.linkedin.com/jobs/view/4422758824/',
        'postingKey': 'linkedin-4422758824',
        'result': 'Archived: requires EE/CE degree with automotive/controls focus. Liam has CS. Must relocate multiple times.',
        'updatedAt': now
    },
]

for item in new_items:
    upsert(item)

s['search']['lastJobUrl'] = 'https://www.linkedin.com/jobs/view/4422758824/'
s['search']['currentResultIndex'] = 9
s['updatedAt'] = now
json.dump(s, open(p, 'w'), indent=2)

items = s['items']
terminal = sum(1 for i in items if i['state'] in ['submitted', 'manual', 'duplicate', 'archived', 'already_applied', 'already_submitted'])
tailor = [i['company'] for i in items if i['state'] == 'tailor_needed']
print('terminal:', terminal, '/ maxJobs:', s['runPolicy']['maxJobs'])
print('tailor_needed:', tailor)
print('visitedUrls count:', len(s['search']['visitedJobUrls']))
