/* ============================================================
   SUG Computer Club – Web Craft
   dynamic-content.js  v2
   Loads published content from Flask/MongoDB API and renders
   it onto the public-facing pages.
   ============================================================ */

(function () {
  'use strict';

  /* ── Global spin animation for loaders ── */
  if (!document.getElementById('dc-spin-style')) {
    const s = document.createElement('style');
    s.id = 'dc-spin-style';
    s.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }

  /* ── Badge CSS injection ── */
  function injectBadgeCSS() {
    if (document.getElementById('dc-badge-style')) return;
    const s = document.createElement('style');
    s.id = 'dc-badge-style';
    s.textContent = `
      .act-tech-badge{display:inline-flex;align-items:center;font-weight:700;border-radius:6px;padding:.25rem .65rem;font-size:.75rem}
      .html-badge{background:rgba(249,115,22,.18);color:#fb923c;border:1px solid rgba(249,115,22,.3)}
      .css-badge{background:rgba(59,130,246,.18);color:#93c5fd;border:1px solid rgba(59,130,246,.3)}
      .js-badge{background:rgba(234,179,8,.18);color:#fde047;border:1px solid rgba(234,179,8,.3)}
      .rwd-badge{background:rgba(20,184,166,.18);color:#5eead4;border:1px solid rgba(20,184,166,.3)}
      .php-badge{background:rgba(139,92,246,.18);color:#c4b5fd;border:1px solid rgba(139,92,246,.3)}
      .int-badge{background:rgba(236,72,153,.18);color:#f9a8d4;border:1px solid rgba(236,72,153,.3)}
      .proj-badge{background:rgba(34,197,94,.18);color:#86efac;border:1px solid rgba(34,197,94,.3)}
      .winners-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1.5rem;margin-top:1.5rem}
      .winner-card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden;text-align:center;padding:1.5rem 1rem;transition:all .25s}
      .winner-card:hover{border-color:rgba(124,58,237,.4);transform:translateY(-3px)}
      .winner-photo{width:80px;height:80px;border-radius:50%;object-fit:cover;margin:0 auto .75rem;display:block;border:3px solid rgba(124,58,237,.4)}
      .winner-photo-placeholder{width:80px;height:80px;border-radius:50%;background:rgba(124,58,237,.18);display:flex;align-items:center;justify-content:center;margin:0 auto .75rem;font-size:1.5rem;font-weight:800;color:#c4b5fd}
      .winner-position{font-size:.75rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:.35rem}
      .pos-1{color:#fde047}.pos-2{color:#e2e8f0}.pos-3{color:#f97316}.pos-other{color:#a9a9d4}
      .winner-name{font-size:1rem;font-weight:700;color:#fff;margin-bottom:.25rem}
      .winner-dept{font-size:.8rem;color:#a9a9d4;margin-bottom:.5rem}
      .winner-event{font-size:.75rem;color:#6b6b9a;font-style:italic}
      .winner-achievement{font-size:.8rem;color:#a9a9d4;margin-top:.5rem;line-height:1.5}
    `;
    document.head.appendChild(s);
  }

  /* ── Helpers ── */
  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function statusClass(s) {
    const map = { Upcoming: 'status-upcoming', Ongoing: 'status-next', Completed: 'status-completed', Cancelled: 'status-upcoming' };
    return map[s] || 'status-upcoming';
  }

  async function fetchJSON(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) return [];
      return await r.json();
    } catch (_) { return []; }
  }

  function reIcons() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  /* ══════════════════════════════════════════════
     EVENTS PAGE — dynamic event cards
     ══════════════════════════════════════════════ */
  const eventsGrid = document.getElementById('dynamic-events-grid');
  if (eventsGrid) {
    injectBadgeCSS();
    fetchJSON('/api/public/events').then(events => {
      if (!events.length) {
        eventsGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:3rem;color:#6b6b9a;font-size:.875rem">
          <i data-lucide="calendar" style="width:36px;height:36px;margin:0 auto .75rem;display:block;opacity:.35"></i>
          No upcoming events at the moment. Check back soon!
        </div>`;
        reIcons(); return;
      }

      eventsGrid.innerHTML = events.map(ev => {
        const badgeHTML = ev.badge
          ? `<span class="act-tech-badge ${esc(ev.badge_class || 'proj-badge')}">${esc(ev.badge)}</span>`
          : '';
        const statusHTML = `<span class="timeline-status ${statusClass(ev.status)}">${esc(ev.status)}</span>`;
        const posterHTML = ev.poster
          ? `<img src="${esc(ev.poster)}" alt="${esc(ev.title)}" loading="lazy"
               style="width:100%;max-height:200px;object-fit:cover;border-radius:10px 10px 0 0;display:block"/>`
          : '';
        const regBtn = ev.reg_link && ev.reg_link !== 'To Be Announced'
          ? `<a href="${esc(ev.reg_link)}" target="_blank" rel="noopener"
               style="display:inline-flex;align-items:center;gap:.4rem;margin-top:.75rem;
                      padding:.5rem 1.1rem;background:linear-gradient(135deg,#4f46e5,#7c3aed);
                      color:#fff;border-radius:999px;font-size:.8rem;font-weight:600;text-decoration:none">
               <i data-lucide="external-link" style="width:13px;height:13px"></i> Register</a>`
          : `<span style="display:inline-block;margin-top:.75rem;font-size:.8rem;color:#6b6b9a">
               <i data-lucide="clock" style="width:13px;height:13px;vertical-align:middle"></i>
               Registration: To Be Announced</span>`;
        const videoHTML = ev.video
          ? (ev.video.includes('youtube') || ev.video.includes('youtu.be')
              ? `<a href="${esc(ev.video)}" target="_blank" rel="noopener"
                   style="display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;color:#c4b5fd;margin-top:.5rem">
                   <i data-lucide="play-circle" style="width:14px;height:14px"></i> Watch on YouTube</a>`
              : `<video src="${esc(ev.video)}" controls
                   style="width:100%;border-radius:8px;margin-top:.75rem;max-height:160px"></video>`)
          : '';

        return `<a href="/event/${esc(ev._id)}" class="event-card" style="display:block;text-decoration:none;color:inherit;cursor:pointer">
          ${posterHTML}
          <div class="event-card-body" ${posterHTML ? 'style="padding-top:.85rem"' : ''}>
            <div class="event-card-top">${badgeHTML}${statusHTML}</div>
            <h3>${esc(ev.title)}</h3>
            <p>${esc(ev.description)}</p>
            ${videoHTML}
            <div class="event-card-footer" style="margin-top:.85rem">
              <span><i data-lucide="calendar" aria-hidden="true"></i> ${esc(ev.date || 'To Be Announced')}</span>
              ${ev.time && ev.time !== 'To Be Announced' ? `<span><i data-lucide="clock" aria-hidden="true"></i> ${esc(ev.time)}</span>` : ''}
              ${ev.venue ? `<span><i data-lucide="map-pin" aria-hidden="true"></i> ${esc(ev.venue)}</span>` : ''}
            </div>
            ${regBtn}
            <div style="margin-top:.75rem;font-size:.78rem;color:#a78bfa;display:flex;align-items:center;gap:.25rem">
              <i data-lucide="info" style="width:12px;height:12px"></i> Click for full details
            </div>
          </div>
        </a>`;
      }).join('');

      reIcons();
    });
  }

  /* ══════════════════════════════════════════════
     WINNERS — shown on events.html
     ══════════════════════════════════════════════ */
  const winnersSection = document.getElementById('winners-section');
  const winnersGrid    = document.getElementById('dynamic-winners-grid');
  if (winnersSection && winnersGrid) {
    injectBadgeCSS();
    fetchJSON('/api/public/winners').then(winners => {
      if (!winners.length) { winnersSection.style.display = 'none'; return; }
      winnersSection.style.display = '';
      const posLabel = { 1: '🥇 1st Place', 2: '🥈 2nd Place', 3: '🥉 3rd Place', 4: 'Runner-Up' };
      const posClass = { 1: 'pos-1', 2: 'pos-2', 3: 'pos-3', 4: 'pos-other' };
      winnersGrid.innerHTML = winners.map(w => {
        const initial = (w.name || 'W')[0].toUpperCase();
        const photoEl = w.photo
          ? `<img class="winner-photo" src="${esc(w.photo)}" alt="${esc(w.name)}" loading="lazy"/>`
          : `<div class="winner-photo-placeholder">${esc(initial)}</div>`;
        return `<a href="/winner/${esc(w._id)}" class="winner-card" style="text-decoration:none;color:inherit;display:block;cursor:pointer">
          ${photoEl}
          <div class="winner-position ${posClass[w.position] || 'pos-other'}">${posLabel[w.position] || 'Participant'}</div>
          <div class="winner-name">${esc(w.name)}</div>
          ${w.department ? `<div class="winner-dept">${esc(w.department)}${w.year ? ' · ' + esc(w.year) : ''}</div>` : ''}
          ${w.event_title ? `<div class="winner-event">${esc(w.event_title)}</div>` : ''}
          ${w.achievement ? `<div class="winner-achievement">${esc(w.achievement)}</div>` : ''}
          <div style="margin-top:.6rem;font-size:.72rem;color:#a78bfa;display:flex;align-items:center;justify-content:center;gap:.25rem">
            <i data-lucide="user" style="width:11px;height:11px"></i> View Profile
          </div>
        </a>`;
      }).join('');
      reIcons();
    });
  }

  /* ══════════════════════════════════════════════
     ACTIVITIES PAGE — dynamic timeline items
     ══════════════════════════════════════════════ */
  const activitiesTimeline = document.getElementById('dynamic-activities-timeline');
  if (activitiesTimeline) {
    injectBadgeCSS();
    fetchJSON('/api/public/activities').then(activities => {
      if (!activities.length) {
        activitiesTimeline.innerHTML = `<div style="text-align:center;padding:3rem;color:#6b6b9a;font-size:.875rem">
          <i data-lucide="layers" style="width:36px;height:36px;margin:0 auto .75rem;display:block;opacity:.35"></i>
          No activities published yet.
        </div>`;
        reIcons(); return;
      }
      activitiesTimeline.innerHTML = activities.map(a => {
        const badgeHTML = a.badge
          ? `<span class="act-tech-badge ${esc(a.badge_class || 'proj-badge')}">${esc(a.badge)}</span>`
          : '';
        const photoHTML = a.photo
          ? `<img src="${esc(a.photo)}" alt="${esc(a.title)}" loading="lazy"
               style="width:100%;max-height:200px;object-fit:cover;border-radius:10px;margin-top:.75rem"/>`
          : '';
        const videoHTML = a.video
          ? (a.video.includes('youtube') || a.video.includes('youtu.be')
              ? `<a href="${esc(a.video)}" target="_blank" rel="noopener"
                   style="display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;color:#c4b5fd;margin-top:.5rem">
                   <i data-lucide="play-circle" style="width:14px;height:14px"></i> Watch Video</a>`
              : `<video src="${esc(a.video)}" controls
                   style="width:100%;border-radius:8px;margin-top:.5rem;max-height:160px"></video>`)
          : '';
        const extLink = a.ext_link
          ? `<a href="${esc(a.ext_link)}" target="_blank" rel="noopener"
               style="display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;color:#38bdf8;margin-top:.4rem">
               <i data-lucide="external-link" style="width:13px;height:13px"></i> More Info</a>`
          : '';

        return `<div class="timeline-item">
          <div class="timeline-dot"></div>
          <div class="timeline-card">
            <div class="timeline-card-top">${badgeHTML}</div>
            <h3>${esc(a.title)}</h3>
            <p>${esc(a.description)}</p>
            ${photoHTML}
            ${videoHTML}
            ${extLink}
            ${a.date ? `<div class="timeline-meta" style="margin-top:.75rem">
              <span><i data-lucide="calendar" aria-hidden="true"></i> ${esc(a.date)}</span>
            </div>` : ''}
          </div>
        </div>`;
      }).join('');
      reIcons();
    });
  }

  /* ══════════════════════════════════════════════
     GALLERY PAGE — dynamic grid
     ══════════════════════════════════════════════ */
  const galleryGrid = document.getElementById('dynamic-gallery-grid');
  if (galleryGrid) {
    fetchJSON('/api/public/gallery').then(items => {
      if (!items.length) {
        galleryGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:3rem;color:#6b6b9a;font-size:.875rem">
          <i data-lucide="image" style="width:36px;height:36px;margin:0 auto .75rem;display:block;opacity:.35"></i>
          Photos and videos will appear here as they are uploaded.
        </div>`;
        reIcons(); return;
      }

      galleryGrid.innerHTML = items.map((item, i) => {
        const isTall = i % 5 === 1 || i % 5 === 4;
        let mediaHTML = '';
        if (item.media_type === 'photo' && item.media_url) {
          mediaHTML = `<img src="${esc(item.media_url)}" alt="${esc(item.caption || '')}" loading="lazy"
                         style="width:100%;height:100%;object-fit:cover;display:block"/>`;
        } else if (item.media_type === 'video' && item.media_url) {
          if (item.media_url.includes('youtube') || item.media_url.includes('youtu.be')) {
            const ytId = item.media_url.match(/(?:v=|youtu\.be\/)([^&?\s]{6,})/)?.[1];
            mediaHTML = ytId
              ? `<iframe src="https://www.youtube.com/embed/${ytId}" frameborder="0" allowfullscreen
                   style="width:100%;height:100%;display:block" title="${esc(item.caption || 'Video')}"></iframe>`
              : `<a href="${esc(item.media_url)}" target="_blank"
                   style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#c4b5fd">
                   <i data-lucide="youtube" style="width:32px;height:32px;color:#f87171"></i></a>`;
          } else {
            mediaHTML = `<video src="${esc(item.media_url)}" controls
                           style="width:100%;height:100%;object-fit:cover;display:block"></video>`;
          }
        } else {
          mediaHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                           width:100%;height:100%;color:#6b6b9a;gap:.35rem">
                         <i data-lucide="image" style="width:28px;height:28px;opacity:.4"></i></div>`;
        }

        return `<div class="gallery-item ${isTall ? 'gallery-item--tall' : ''}"
                     data-category="${esc(item.category || 'General')}">
          ${mediaHTML}
          <span>${esc(item.caption || item.category || 'Web Craft')}</span>
        </div>`;
      }).join('');

      reIcons();

      // Hook into existing filter buttons
      document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const filter = btn.textContent.trim();
          document.querySelectorAll('#dynamic-gallery-grid .gallery-item').forEach(item => {
            const cat = item.dataset.category || '';
            item.style.display = (filter === 'All' || cat.toLowerCase().includes(filter.toLowerCase())) ? '' : 'none';
          });
        });
      });
    });
  }

})();
