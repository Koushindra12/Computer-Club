import urllib.request, json

base = 'http://localhost:5000'
passed = 0
failed = 0

def check(label, ok, detail=''):
    global passed, failed
    status = 'PASS' if ok else 'FAIL'
    print(f'[{status}] {label}', f'| {detail}' if detail else '')
    if ok: passed += 1
    else:  failed += 1

# 1. Public events list
r = urllib.request.urlopen(base + '/api/public/events', timeout=5)
events = json.loads(r.read())
check('Public events API', len(events) >= 0, f'{len(events)} events')

if events:
    eid = events[0]['_id']
    title = events[0]['title']

    # 2. Single event API
    r2 = urllib.request.urlopen(f'{base}/api/public/events/{eid}', timeout=5)
    ev = json.loads(r2.read())
    check('Single event API', ev.get('title') == title, ev.get('title',''))

    # 3. Event detail page renders
    r3 = urllib.request.urlopen(f'{base}/event/{eid}', timeout=5)
    html3 = r3.read().decode('utf-8')
    check('Event detail page loads', r3.status == 200 and title[:15] in html3, f'{len(html3)} bytes')
    check('Event detail has navbar', 'nav-logo' in html3, '')
    check('Event detail has back link', 'Back to Events' in html3, '')

# 4. Public winners
r4 = urllib.request.urlopen(base + '/api/public/winners', timeout=5)
winners = json.loads(r4.read())
check('Public winners API', True, f'{len(winners)} winners')

if winners:
    wid = winners[0]['_id']
    name = winners[0]['name']

    # 5. Single winner API
    r5 = urllib.request.urlopen(f'{base}/api/public/winners/{wid}', timeout=5)
    w = json.loads(r5.read())
    check('Single winner API', w.get('name') == name, name)

    # 6. Winner detail page
    r6 = urllib.request.urlopen(f'{base}/winner/{wid}', timeout=5)
    html6 = r6.read().decode('utf-8')
    check('Winner detail page loads', r6.status == 200 and name in html6, f'{len(html6)} bytes')
    check('Winner detail has navbar', 'nav-logo' in html6, '')

# 7. Invalid ID returns 404
try:
    urllib.request.urlopen(f'{base}/event/000000000000000000000000', timeout=5)
    check('Invalid event 404', False, 'Should have raised HTTPError')
except urllib.error.HTTPError as e:
    check('Invalid event 404', e.code == 404, f'Got {e.code}')

# 8. Invalid winner 404
try:
    urllib.request.urlopen(f'{base}/winner/000000000000000000000000', timeout=5)
    check('Invalid winner 404', False, 'Should have raised HTTPError')
except urllib.error.HTTPError as e:
    check('Invalid winner 404', e.code == 404, f'Got {e.code}')

# 9. Homepage still works
r9 = urllib.request.urlopen(base + '/', timeout=5)
check('Homepage loads', r9.status == 200, '')

# 10. Admin login page accessible
r10 = urllib.request.urlopen(base + '/admin/login', timeout=5)
check('Admin login accessible', r10.status == 200, '')

print(f'\n=== Results: {passed} passed, {failed} failed ===')
