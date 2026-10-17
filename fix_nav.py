"""Fix the two pages that the initial script couldn't patch."""

ADMIN_NAV = (
    '\n        <li role="none">'
    '<a href="/admin/login" class="nav-link nav-admin-link" '
    'role="menuitem" title="Admin Dashboard">'
    '<i data-lucide="shield" aria-hidden="true"></i>'
    ' Admin</a>'
    '</li>'
)

FOOTER_ADMIN = (
    '<a href="/admin/login" '
    'style="display:inline-flex;align-items:center;gap:.3rem;'
    'margin-left:1rem;color:rgba(255,255,255,.35);font-size:.75rem;'
    'text-decoration:none;transition:color .2s" '
    'title="Admin Login">'
    '<i data-lucide="shield" style="width:12px;height:12px"></i>'
    ' Admin</a>'
)

# ── index.html footer fix ─────────────────────────────────────────────────────
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

if 'nav-admin-link' not in html:
    print('[WARN] index.html nav already handled or missing – skipped')

# Footer: find the </p> inside footer-bottom and insert after it
FOOTER_MARKER = 'footer-bottom">'
idx = html.find(FOOTER_MARKER)
if idx != -1:
    p_end = html.find('</p>', idx)
    if p_end != -1 and FOOTER_ADMIN not in html:
        html = html[:p_end + 4] + FOOTER_ADMIN + html[p_end + 4:]
        print('[FOOT] fixed index.html footer')
    else:
        print('[OK]  index.html footer already has admin link')
else:
    print('[WARN] footer-bottom not found in index.html')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

# ── members.html nav fix ──────────────────────────────────────────────────────
with open('members.html', 'r', encoding='utf-8') as f:
    html = f.read()

if 'nav-admin-link' in html:
    print('[OK]  members.html nav already has admin link')
else:
    # The Join Club button spans multiple lines; find </li> that closes it
    # and inject after it
    MULTILINE_JOIN_END = '          </button>\n        </li>'
    if MULTILINE_JOIN_END in html:
        html = html.replace(
            MULTILINE_JOIN_END,
            MULTILINE_JOIN_END + ADMIN_NAV,
            1
        )
        print('[NAV] fixed members.html nav')
    else:
        # Fallback: inject before </ul> in the nav-menu
        html = html.replace(
            '<ul class="nav-menu" id="nav-menu"',
            '<ul class="nav-menu" id="nav-menu"',
            1
        )
        # Try inserting before the closing </ul> of nav-menu
        NAV_UL_CLOSE = '      </ul>\n\n    </div>\n\n    <div'
        if NAV_UL_CLOSE in html and 'nav-admin-link' not in html:
            html = html.replace(
                NAV_UL_CLOSE,
                ADMIN_NAV + '\n      </ul>\n\n    </div>\n\n    <div',
                1
            )
            print('[NAV] fixed members.html nav (fallback)')
        else:
            print('[WARN] Could not inject nav into members.html')

if FOOTER_ADMIN not in html:
    FOOTER_MARKER = 'footer-bottom">'
    idx = html.find(FOOTER_MARKER)
    if idx != -1:
        p_end = html.find('</p>', idx)
        if p_end != -1:
            html = html[:p_end + 4] + FOOTER_ADMIN + html[p_end + 4:]
            print('[FOOT] fixed members.html footer')
else:
    print('[OK]  members.html footer already has admin link')

with open('members.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('\nDone.')
