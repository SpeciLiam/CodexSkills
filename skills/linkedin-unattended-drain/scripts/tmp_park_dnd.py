import json
from datetime import datetime, timezone

p = '/tmp/linkedin_unattended_drain_state.json'
s = json.load(open(p))
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')

for i, it in enumerate(s['items']):
    if it['key'] == 'linkedin-4426546692':
        s['items'][i].update({
            'state': 'manual',
            'blocker': 'file_upload sandbox rejects companies/ path; mcp__ccd_directory disconnected in resumed session. PDF verified 1-page at Liam_Van_DND_Solutions.pdf. Handoff entry written.',
            'updatedAt': now
        })
        break

s['updatedAt'] = now
json.dump(s, open(p, 'w'), indent=2)

terminal = sum(1 for i in s['items'] if i['state'] in ['submitted', 'manual', 'duplicate', 'archived', 'already_applied', 'already_submitted'])
print('DND parked as manual. terminal:', terminal)
print('tailor_needed:', [i['company'] for i in s['items'] if i['state'] == 'tailor_needed'])
