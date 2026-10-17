with open('activities.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Rebuild: keep section header (lines 0-63), replace timeline items with dynamic container,
# then continue from the section close (line 183+)
keep_before = lines[:64]

dynamic_block = [
    '\n',
    '      <!-- Activities are loaded dynamically from the Admin Dashboard -->\n',
    '      <div id="dynamic-activities-timeline" class="timeline" data-animate="fade-up">\n',
    '        <div style="text-align:center;padding:2rem;color:#6b6b9a;font-size:.875rem">\n',
    '          <i data-lucide="loader" style="width:24px;height:24px;margin:0 auto .5rem;display:block;opacity:.5;animation:spin 1s linear infinite"></i>\n',
    '          Loading activities\u2026\n',
    '        </div>\n',
    '      </div>\n',
    '    </div>\n',
    '  </section>\n',
    '\n',
]

# Find the CTA section after the activities content
cta_idx = None
for i, line in enumerate(lines):
    if 'cta-section' in line and i > 100:
        cta_idx = i
        break

if cta_idx is None:
    raise ValueError('Could not find CTA section in activities.html')

keep_after = lines[cta_idx:]
new_lines = keep_before + dynamic_block + keep_after

with open('activities.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Done. New total: {len(new_lines)} lines.')
for i, l in enumerate(new_lines[63:76], start=64):
    print(f'{i}: {l.rstrip()}')
