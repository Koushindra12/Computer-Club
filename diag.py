with open('js/dynamic-content.js','r',encoding='utf-8') as f:
    c = f.read()
idx = c.find('return `<div class="event-card">')
print('Event card start idx:', idx)
if idx >= 0:
    print(repr(c[idx:idx+300]))
idx2 = c.find("return `<div class=\"winner-card\">")
print('Winner card start idx:', idx2)
if idx2 >= 0:
    print(repr(c[idx2:idx2+300]))
