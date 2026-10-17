"""
add_admin_nav.py
Adds "Admin Login" button to the navbar and a small footer link
across all public HTML pages. Run once.
"""

import os, re

PAGES = [
    'index.html', 'about.html', 'activities.html',
    'events.html', 'gallery.html', 'members.html', 'contact.html'
]

# The nav item to inject – placed right after the Join Club li
NAV_ITEM = (
    '<li role="none">'
    '<a href="/admin/login" class="nav-link nav-admin-link" '
    'role="menuitem" title="Admin Dashboard">'
    '<i data-lucide="shield" aria-hidden="true"></i>'
    ' Admin</a>'
    '</li>'
)

# Old Join Club li (exact pattern present in every page)
JOIN_PATTERN = (
    '<li role="none"><button onclick="openJoinModal()" '
    'class="btn btn-primary nav-cta" role="menuitem">Join Club</button></li>'
)
JOIN_REPLACEMENT = JOIN_PATTERN + '\n        ' + NAV_ITEM

# Footer Admin link – injected after footer-bottom copyright paragraph
FOOTER_ADMIN = (
    '<a href="/admin/login" '
    'style="display:inline-flex;align-items:center;gap:.3rem;'
    'margin-left:1rem;color:rgba(255,255,255,.35);font-size:.75rem;'
    'text-decoration:none;transition:color .2s" '
    'title="Admin Login">'
    '<i data-lucide="shield" style="width:12px;height:12px"></i>'
    ' Admin</a>'
)

# Locate the copyright paragraph in footer-bottom and append link after </p>
COPYRIGHT_PATTERN = re.compile(
    r'(<p>&copy;[^<]+</p>)',
    re.DOTALL
)

changed = []

for page in PAGES:
    if not os.path.exists(page):
        print(f'  SKIP {page} (not found)')
        continue

    with open(page, 'r', encoding='utf-8') as f:
        html = f.read()

    original = html

    # 1. Nav item
    if NAV_ITEM in html:
        print(f'  [OK] nav already present: {page}')
    elif JOIN_PATTERN in html:
        html = html.replace(JOIN_PATTERN, JOIN_REPLACEMENT, 1)
        print(f'  [NAV] added admin nav: {page}')
    else:
        print(f'  [WARN] Join Club pattern not found in {page} - skipping nav')

    # 2. Footer link
    if 'nav-admin-link' in html and '/admin/login' in html and 'Admin</a>' in html.split('footer-bottom')[1] if 'footer-bottom' in html else True:
        pass
    if FOOTER_ADMIN in html:
        print(f'  [OK] footer already present: {page}')
    else:
        new_html, n = COPYRIGHT_PATTERN.subn(
            r'\1' + FOOTER_ADMIN,
            html, count=1
        )
        if n:
            html = new_html
            print(f'  [FOOT] added admin footer: {page}')
        else:
            print(f'  [WARN] footer copyright not found: {page}')

    if html != original:
        with open(page, 'w', encoding='utf-8') as f:
            f.write(html)
        changed.append(page)

print(f'\nDone. Modified {len(changed)} file(s): {", ".join(changed)}')
