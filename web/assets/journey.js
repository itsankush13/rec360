/* Recruitment 360 journey workspaces. One campaign, real lifecycle data. */
(function () {
  var page = document.body.dataset.journeyPage;
  if (!page) return;
  var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
  var campaignId = '';
  var people = [];
  var lifecycle = [];
  var candidates = [];
  var costCentres = [];
  var selection = '';
  var key = 'recruitment360.campaign';
  var emailMode = null; // 'outlook' | 'simulated' | null (unknown) — offers use the EMAIL backend

  // Truthfulness fix (2026-09-14 demo): the offer badge used to hardcode
  // "SIMULATED". It now asks the API which backend is really active, so it
  // cannot lie once Outlook goes live. See app/api/offers.py — an offer
  // send reuses the same mail adapter as messages.
  if (page === 'offer') {
    window.__r360ApplySendBadge(document.getElementById('offer-sendbadge'), null, 'email', {
      realBadge: 'SENDS FOR REAL — OUTLOOK LIVE · a real letter email is sent',
      simBadge: 'SIMULATED — INTEGRATION PENDING · no letter or email sent',
    });
    window.__r360SendMode('email').then(function (mode) { emailMode = mode; renderOfferActions(); });
  }
  function el(id) { return document.getElementById(id); }
  function esc(value) { return String(value == null ? '' : value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
  function say(id, value) { if (el(id)) el(id).textContent = value; }
  function show(id, visible) { if (el(id)) el(id).hidden = !visible; }
  function words(status) { return String(status || '').replace(/_/g,' ').toLowerCase().replace(/^\w/,function(c){return c.toUpperCase();}); }
  function request(path, options) {
    return fetch(base + path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : (body.error && body.error.message) || 'Request failed (' + response.status + ')');
        return body;
      });
    });
  }
  function post(path, payload) { return request(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); }
  function options(rows, selected) { return rows.map(function (row) { return '<option value="' + esc(row.id) + '"' + (row.id === selected ? ' selected' : '') + '>' + esc(row.full_name || row.name || row.id) + '</option>'; }).join(''); }
  function dateDays(n) { var d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0,10); }
  function statusRow(id) { return lifecycle.find(function (row) { return row.candidate_id === id; }); }
  function candidateName(id) { var c = candidates.find(function (item) { return item.id === id; }); return c ? c.full_name : id; }
  function candidateEmail(id) { var c = candidates.find(function (item) { return item.id === id; }); return (c && c.email) || ''; }
  function chart(rows, total) {
    var max = Math.max.apply(null, rows.map(function (r) { return r.count; }).concat([1]));
    el('journey-chart').innerHTML = rows.map(function (r) {
      var width = Math.round(100 * r.count / max);
      return '<div class="journey-bar"><span>' + esc(r.label) + '</span><div class="journey-track"><i style="width:' + width + '%"></i></div><b>' + r.count + '<small> / ' + total + '</small></b></div>';
    }).join('');
  }
  function fillSelectors(allowed) {
    var target = el('candidate-select');
    if (!target) return;
    var rows = lifecycle.filter(function (row) { return allowed.indexOf(row.status) !== -1; });
    target.innerHTML = '<option value="">Choose candidate…</option>' + rows.map(function (row) {
      return '<option value="' + esc(row.candidate_id) + '">' + esc(candidateName(row.candidate_id)) + ' · ' + esc(row.status_label || words(row.status)) + '</option>';
    }).join('');
    if (rows.some(function (row) { return row.candidate_id === selection; })) target.value = selection;
    else selection = '';
    var actor = el('actor-select');
    actor.innerHTML = '<option value="">Choose acting person…</option>' + options(people);
    var me = window.__r360Me;
    var remembered = localStorage.getItem('recruitment360.actor');
    if (me && people.some(function (p) { return p.id === me.id; })) actor.value = me.id;
    else if (people.some(function (p) { return p.id === remembered; })) actor.value = remembered;
    actor.onchange = function () { localStorage.setItem('recruitment360.actor', actor.value); };
    // B25: the budget approver only ever acts as themselves.
    actor.disabled = !!(me && me.role === 'REVIEWER' && actor.value === me.id);
  }
  function selectedActor() { var id = el('actor-select').value; if (!id) throw new Error('Choose the acting person first.'); return id; }
  function selectedCandidate() { if (!selection) throw new Error('Choose a candidate first.'); return selection; }
  function act(path, payload) {
    say('action-message','Saving the decision…');
    post('/api/campaigns/' + encodeURIComponent(campaignId) + path, payload)
      .then(function () { say('action-message','Saved to the candidate record.'); refresh(); })
      .catch(function (error) { say('action-message',error.message); });
  }
  function renderPipeline(data) {
    var funnel = data.funnel || [];
    var total = funnel.length ? funnel[0].of : 0;
    var active = funnel.filter(function (r) { return r.count; });
    var hired = data.outcomes.hired.count;
    say('journey-headline', total ? (hired ? hired + ' hired so far' : active.length + ' active stages') : 'No candidates in the hiring journey yet');
    say('journey-summary', total ? total + ' candidates have entered the hiring journey. Select a workspace below to move work forward.' : 'Shortlist a candidate first. Their position will appear here.');
    chart(active.length ? active : funnel.slice(0,6), total);
    el('journey-raw').innerHTML = funnel.map(function (r) { return '<div class="journey-raw"><span>' + esc(r.label) + '</span><b>' + r.count + ' of ' + r.of + '</b></div>'; }).join('');
    var b = data.bottleneck;
    show('journey-bottleneck',!!b);
    if (b) { say('bottleneck-headline', b.label + ' takes longest'); say('bottleneck-summary', b.median_days + ' median days across ' + b.count + ' completed stays; ' + b.now_here + ' candidates there now.'); }
    el('journey-times').innerHTML = (data.time_in_stage || []).map(function (r) { return '<div class="journey-raw"><span>' + esc(r.label) + '</span><b>' + r.median_days + ' median days · ' + r.count + ' stays</b></div>'; }).join('');
    show('journey-surface',true);
  }
  // Closing the campaign itself (Campaign.status -> CLOSED) is a separate
  // concept from any candidate's own lifecycle status — see
  // app/db/models.py's CampaignStatus. CLOSED is terminal (no transition out
  // of it), so this is fetched fresh rather than trusted from a stale cache.
  function renderCampaignClose(campaign) {
    var closed = campaign.status === 'CLOSED';
    show('campaign-close', true);
    show('campaign-closed-tag', closed);
    show('close-campaign-btn', !closed);
    if (closed) show('close-campaign-form', false);
  }
  function loadCampaignClose() {
    request('/api/campaigns/' + encodeURIComponent(campaignId)).then(renderCampaignClose)
      .catch(function () { show('campaign-close', false); });
  }
  function renderApprovals(queue) {
    var counts = [{label:'Awaiting HR', count:queue.filter(function (r){return r.status === 'PENDING_APPROVAL';}).length}, {label:'Awaiting budget', count:queue.filter(function (r){return r.status === 'PENDING_COST_CENTRE';}).length}];
    say('journey-headline',queue.length ? queue.length + ' decisions waiting' : 'No approvals waiting');
    say('journey-summary',queue.length ? 'Open the queue to see owners and reasons, or choose a candidate to record the next step.' : 'When interview feedback is complete, request the named approval below.');
    chart(counts,lifecycle.length);
    el('approval-queue').innerHTML = queue.length ? queue.map(function (r) { return '<div class="journey-raw"><span><b>' + esc(r.candidate_name) + '</b><br>' + esc(r.owner_name || 'Owner not named') + ' · ' + r.days_waiting + ' days waiting<br><small>' + esc(r.justification || '') + '</small></span><b>' + esc(words(r.status)) + '</b></div>'; }).join('') : '<p>No pending decisions.</p>';
    // B25: the budget approver only ever acts on candidates already waiting
    // on them — HR's own request/cost-centre-routing steps aren't theirs to
    // see or touch.
    var isBudgetApprover = window.__r360Me && window.__r360Me.role === 'REVIEWER';
    fillSelectors(isBudgetApprover ? ['PENDING_COST_CENTRE'] : ['FEEDBACK_COMPLETE','PENDING_APPROVAL','PENDING_COST_CENTRE']);
    renderApprovalActions(); show('journey-surface',true);
  }
  function centreLabel(c) { return c.code + ' — ' + (c.business_unit || c.name || 'No BU named') + ' (' + c.currency + ')'; }
  function envelopeCard(c) {
    if (!c) return '';
    var holder = people.find(function (p) { return p.id === c.budget_holder_id; });
    var band = (c.salary_band_min != null && c.salary_band_max != null)
      ? c.currency + ' ' + c.salary_band_min.toLocaleString() + ' – ' + c.salary_band_max.toLocaleString()
      : 'Not stated';
    return '<div class="journey-envelope"><p class="journey-simulated">ILLUSTRATIVE — synthetic pre-approved allocation for this demo, not a live ERP feed</p>' +
      '<div class="journey-raw"><span>Business unit</span><b>' + esc(c.business_unit || 'Not named') + '</b></div>' +
      '<div class="journey-raw"><span>Cost centre</span><b>' + esc(c.code) + ' · ' + esc(c.name || '') + '</b></div>' +
      '<div class="journey-raw"><span>Budget holder</span><b>' + esc(holder ? holder.full_name : c.budget_holder_id) + '</b></div>' +
      '<div class="journey-raw"><span>Fiscal period</span><b>' + esc(c.fiscal_year || 'Not stated') + '</b></div>' +
      '<div class="journey-raw"><span>Approved requisition</span><b>' + esc(c.role_grade || 'Not stated') + (c.approved_headcount != null ? ' · headcount ' + c.approved_headcount : '') + '</b></div>' +
      '<div class="journey-raw"><span>Approved salary band</span><b>' + esc(band) + '</b></div></div>';
  }
  function renderApprovalActions() {
    var row = statusRow(selection);
    var box = el('approval-actions');
    if (!row) { box.innerHTML = '<p class="journey-muted">Choose a candidate to see the next step.</p>'; return; }
    var approvers = people.filter(function (p) { return p.role === 'REVIEWER' || p.role === 'ADMIN' || p.role === 'HIRING_MANAGER'; });
    if (row.status === 'FEEDBACK_COMPLETE') box.innerHTML = '<form data-action="request"><label>First approver<select name="approver" required><option value="">Choose approver…</option>' + options(approvers) + '</select></label><label>Grade<input name="grade"></label><label>Salary band<input name="salary_band"></label><label>Justification<textarea name="justification" required></textarea></label><button class="cta" type="submit">Request approval</button></form>';
    else if (row.status === 'PENDING_APPROVAL') {
      box.innerHTML = '<form data-action="cost-centre"><label>Cost centre (BU pre-approved envelope)<select name="cost_centre_code" required><option value="">Choose cost centre…</option>' + costCentres.map(function (c) { return '<option value="' + esc(c.code) + '">' + esc(centreLabel(c)) + '</option>'; }).join('') + '</select></label><input type="hidden" name="budget_holder_id"><div id="cc-envelope-preview"></div><button class="cta" type="submit">Send for budget sign-off</button></form><details><summary>Return to HR discussion</summary><form data-action="return"><label>Reason<textarea name="reason" required></textarea></label><button class="ghost" type="submit">Return decision</button></form></details>';
      var select = box.querySelector('[name="cost_centre_code"]'), hidden = box.querySelector('[name="budget_holder_id"]');
      select.onchange = function () {
        var chosen = costCentres.find(function (c) { return c.code === select.value; });
        hidden.value = chosen ? chosen.budget_holder_id : '';
        el('cc-envelope-preview').innerHTML = envelopeCard(chosen);
      };
    }
    else if (row.status === 'PENDING_COST_CENTRE') {
      // B25: granting the budget belongs to the budget approver (REVIEWER)
      // alone — WHO_MAY already refuses the API call for anyone else, but
      // the form itself is hidden too, so the interface matches what the
      // signed-in role can actually do rather than failing after a click.
      var isBudgetApprover = window.__r360Me && window.__r360Me.role === 'REVIEWER';
      box.innerHTML = isBudgetApprover
        ? '<form data-action="grant"><label>Approval note<textarea name="note"></textarea></label><button class="cta" type="submit">Grant approval</button></form><details><summary>Return to approver</summary><form data-action="return"><label>Reason<textarea name="reason" required></textarea></label><button class="ghost" type="submit">Return decision</button></form></details>'
        : '<p class="journey-muted">Waiting on the budget approver to grant or return this.</p>';
    }
    else box.innerHTML = '<p class="journey-muted">Nothing to record at this step.</p>';
  }
  function renderOffers(offers) {
    var drafted = offers.filter(function (r){return r.status === 'OFFER_DRAFTED';}).length;
    var awaiting = offers.filter(function (r){return r.status === 'OFFER_SENT';}).length;
    var accepted = offers.filter(function (r){return r.status === 'OFFER_ACCEPTED' || r.status === 'HIRED';}).length;
    say('journey-headline', offers.length ? awaiting + (awaiting === 1 ? ' offer' : ' offers') + ' recorded as sent' : 'No offers yet');
    say('journey-summary', offers.length ? 'Drafted offers stay separate from offers recorded as sent. Open the list for package and expiry details.' : 'Start with an approved candidate. The package and every revision will be recorded.');
    chart([{label:'Drafted',count:drafted},{label:'Recorded as sent',count:awaiting},{label:'Accepted',count:accepted}],offers.length);
    el('offer-list').innerHTML = offers.length ? offers.map(function (r) { return '<div class="journey-raw"><span><b>' + esc(r.candidate_name) + '</b><br>' + esc(r.status_label) + (r.expiry_date ? ' · expires ' + esc(r.expiry_date) : '') + '</span><b>' + esc(r.currency) + ' ' + esc(r.total_package) + '</b></div>'; }).join('') : '<p>No offers recorded.</p>';
    fillSelectors(['APPROVED','OFFER_DRAFTED','OFFER_SENT']);
    renderOfferActions(); show('journey-surface',true);
  }
  function renderOfferActions() {
    var row = statusRow(selection), box = el('offer-actions');
    if (!row) { box.innerHTML = '<p class="journey-muted">Choose a candidate to see the next step.</p>'; return; }
    if (row.status === 'APPROVED' || row.status === 'OFFER_DRAFTED') {
      var revision = row.status === 'OFFER_DRAFTED';
      // Truthfulness fix (2026-09-14 demo): this used to hardcode "No email
      // is transmitted." Offer send reuses the mail adapter (app/api/offers.py),
      // so once EMAIL_BACKEND=outlook it genuinely sends a letter email.
      var sendNote = emailMode === 'outlook'
        ? 'A real letter email is sent to the candidate.'
        : emailMode === 'simulated'
          ? 'No email is transmitted.'
          : 'Could not confirm the email send mode — treat this as if it may send for real.';
      box.innerHTML = '<form data-action="' + (revision ? 'revise' : 'draft') + '"><label>Base salary<input name="base_salary" type="number" min="0.01" step="0.01" required></label><label>Currency<input name="currency" value="QAR" required></label><label>Grade<input name="grade"></label><label>Start date<input name="start_date" type="date" value="' + dateDays(30) + '" required></label><label>Expiry date<input name="expiry_date" type="date" value="' + dateDays(10) + '" required></label><label>Notes<textarea name="notes"></textarea></label><button class="cta" type="submit">' + (revision ? 'Save revision' : 'Draft offer') + '</button></form>' + (revision ? '<details><summary>Record offer as sent</summary><p>' + esc(sendNote) + '</p><label>Send to<input name="offer_recipient" id="offer-recipient" list="offer-proxy-list" value="' + esc(candidateEmail(selection)) + '"></label><datalist id="offer-proxy-list"><option value="daipayan.r@protivitiglobal.in" label="Daipayan"><option value="chiranjib.sarma@protivitiglobal.in" label="Chiranjib"><option value="preetam.c@protivitiglobal.me" label="Preetam"><option value="ankush.saxena@protivitiglobal.in" label="Ankush"><option value="subhadeep.m@protivitiglobal.in" label="Subhadeep"></datalist><button class="cta" data-offer-send type="button">Record send</button></details>' : '');
    } else box.innerHTML = '<form data-action="response"><label>Candidate answer<select name="response"><option value="ACCEPTED">Accepted</option><option value="DECLINED">Declined</option></select></label><label>Reason code if declined<select name="reason_code"><option value="">Choose if declined…</option><option>COMPENSATION</option><option>COUNTER_OFFER</option><option>LOCATION</option><option>TIMING</option><option>ROLE_SCOPE</option><option>OTHER</option></select></label><label>Reason if declined<textarea name="reason"></textarea></label><button class="cta" type="submit">Record answer</button></form>';
  }
  function refresh() {
    if (!campaignId) return;
    say('load-message','Loading current campaign…');
    var common = [request('/api/users'),request('/api/campaigns/' + encodeURIComponent(campaignId) + '/lifecycle'),request('/api/campaigns/' + encodeURIComponent(campaignId) + '/candidates')];
    if (page === 'approvals') common.push(request('/api/cost-centres'));
    var detail = page === 'pipeline' ? '/metrics/overview' : page === 'approvals' ? '/approvals/queue' : '/offers';
    Promise.all(common.concat([request('/api/campaigns/' + encodeURIComponent(campaignId) + detail)])).then(function (parts) {
      people = parts[0] || []; lifecycle = parts[1] || []; candidates = parts[2] || [];
      var detailIndex = 3;
      if (page === 'approvals') { costCentres = parts[3] || []; detailIndex = 4; }
      if (page === 'pipeline') { renderPipeline(parts[detailIndex]); loadCampaignClose(); }
      if (page === 'approvals') renderApprovals(parts[detailIndex]);
      if (page === 'offer') renderOffers(parts[detailIndex]);
      say('load-message','Current data');
    }).catch(function (error) { show('journey-surface',false); show('campaign-close',false); say('load-message','Could not load campaign: ' + error.message); });
  }
  el('campaign-select').onchange = function () { campaignId = this.value; localStorage.setItem(key,campaignId); show('journey-surface',false); show('campaign-close',false); refresh(); };
  if (el('close-campaign-btn')) {
    el('close-campaign-btn').addEventListener('click', function () {
      el('close-campaign-err').hidden = true;
      show('close-campaign-form', true);
    });
    el('close-campaign-cancel').addEventListener('click', function () { show('close-campaign-form', false); });
    el('close-campaign-confirm').addEventListener('click', function () {
      // B28: closing a campaign is HR's call, not the hiring manager's —
      // he can see the current position (renderCampaignClose above still
      // runs for him) but the confirm button refuses to fire.
      if (window.__r360Locked && window.__r360Locked()) {
        var err = el('close-campaign-err');
        err.textContent = 'View only — closing a campaign isn\'t your decision to make.';
        err.hidden = false;
        return;
      }
      post('/api/campaigns/' + encodeURIComponent(campaignId) + '/status', { status: 'CLOSED' })
        .then(function () { show('close-campaign-form', false); loadCampaignClose(); })
        .catch(function (error) {
          var err = el('close-campaign-err');
          err.textContent = error.message;
          err.hidden = false;
        });
    });
  }
  if (el('candidate-select')) el('candidate-select').onchange = function () { selection = this.value; say('action-message',''); if (page === 'approvals') renderApprovalActions(); else renderOfferActions(); };
  if (el('approval-actions')) el('approval-actions').addEventListener('submit',function (event) {
    event.preventDefault();
    // B28: budget/cost-centre routing is HR's and the budget approver's
    // job (B25) — the hiring manager can watch the queue but not act on it.
    if (window.__r360Locked && window.__r360Locked()) { say('action-message',"View only — this isn't your decision to make."); return; }
    try {
      var form = event.target, data = Object.fromEntries(new FormData(form));
      var actor = selectedActor(), candidate = selectedCandidate(), action = form.dataset.action;
      var body = {actor_id:actor};
      if (action === 'request') body = {actor_id:actor,chain:[data.approver],grade:data.grade,salary_band:data.salary_band,justification:data.justification};
      if (action === 'cost-centre') body = {actor_id:actor,cost_centre_code:data.cost_centre_code,budget_holder_id:data.budget_holder_id};
      if (action === 'grant') body.note = data.note;
      if (action === 'return') body.reason = data.reason;
      act('/approvals/' + candidate + '/' + action,body);
    } catch (error) { say('action-message',error.message); }
  });
  if (el('offer-actions')) {
    el('offer-actions').addEventListener('submit',function (event) {
      event.preventDefault();
      // B28: drafting/sending an offer is HR's job, not the hiring manager's.
      if (window.__r360Locked && window.__r360Locked()) { say('action-message',"View only — this isn't your decision to make."); return; }
      try {
        var form = event.target, data = Object.fromEntries(new FormData(form));
        var actor = selectedActor(), candidate = selectedCandidate(), action = form.dataset.action;
        var body = {actor_id:actor};
        if (action === 'draft' || action === 'revise') body = {actor_id:actor,base_salary:Number(data.base_salary),currency:data.currency,grade:data.grade,start_date:data.start_date,expiry_date:data.expiry_date,notes:data.notes};
        if (action === 'response') body = {actor_id:actor,response:data.response,reason:data.reason,reason_code:data.reason_code || null};
        act('/offers/' + candidate + '/' + action,body);
      } catch (error) { say('action-message',error.message); }
    });
    el('offer-actions').addEventListener('click',function (event) {
      if (!event.target.matches('[data-offer-send]')) return;
      if (window.__r360Locked && window.__r360Locked()) { say('action-message',"View only — this isn't your decision to make."); return; }
      try {
        var to = el('offer-recipient');
        act('/offers/' + selectedCandidate() + '/send',
            {actor_id:selectedActor(), recipient: to ? to.value.trim() : ''});
      }
      catch (error) { say('action-message',error.message); }
    });
  }
  request('/api/campaigns').then(function (rows) {
    el('campaign-select').innerHTML = '<option value="">Choose a campaign…</option>' + campaignOptions(rows).map(function (option) { return '<option value="' + esc(option.id) + '">' + esc(option.label) + '</option>'; }).join('');
    var wanted = new URLSearchParams(location.search).get('campaign') || localStorage.getItem(key);
    if ((rows || []).some(function (row){return row.id === wanted;})) { campaignId = wanted; el('campaign-select').value = wanted; refresh(); }
    else say('load-message', rows.length ? 'Choose a campaign to begin.' : 'No campaigns yet. Create one first.');
  }).catch(function (error) { say('load-message','Could not load campaigns: ' + error.message); });
})();
