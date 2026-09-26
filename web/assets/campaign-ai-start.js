(function () {
  var form = document.getElementById('ai-start-form');
  if (!form) return;

  var textarea = document.getElementById('ai-start-request');
  var submitBtn = document.getElementById('ai-start-submit');
  var statusEl = document.getElementById('ai-start-status');
  var errorEl = document.getElementById('ai-start-error');
  var review = document.getElementById('ai-review');
  var folderInput = document.getElementById('ai-start-folder');
  var filesInput = document.getElementById('ai-start-files');
  var locationInput = document.getElementById('ai-start-location');
  var resumeNote = document.getElementById('ai-start-resume-note');

  var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');

  function chosenResumeFiles() {
    var files = [];
    if (folderInput && folderInput.files) Array.prototype.push.apply(files, folderInput.files);
    if (filesInput && filesInput.files) Array.prototype.push.apply(files, filesInput.files);
    return files;
  }

  function describeChosenFiles() {
    var n = chosenResumeFiles().length;
    resumeNote.textContent = n ? n + ' file' + (n === 1 ? '' : 's') + ' chosen.' : '';
  }

  if (folderInput) folderInput.addEventListener('change', describeChosenFiles);
  if (filesInput) filesInput.addEventListener('change', describeChosenFiles);

  function node(tag, text, cls) {
    var el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }

  function setBusy(busy) {
    submitBtn.disabled = busy;
    textarea.disabled = busy;
    statusEl.classList.toggle('on', busy);
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.add('on');
  }

  function clearError() {
    errorEl.textContent = '';
    errorEl.classList.remove('on');
  }

  async function readErrorDetail(response) {
    try {
      var body = await response.json();
      if (typeof body.detail === 'string') return body.detail;
      if (Array.isArray(body.detail) && body.detail[0]) {
        return body.detail[0].msg || 'The request could not be understood.';
      }
    } catch (e) { /* fall through */ }
    return 'Something went wrong preparing the campaign. Please try again.';
  }

  function understoodTile(label, value) {
    var tile = node('div', '', 'u');
    tile.appendChild(node('div', label, 'k'));
    tile.appendChild(node('div', value, 'v'));
    return tile;
  }

  function chipsRow(label, items) {
    var wrap = node('div', '', 'u');
    wrap.appendChild(node('div', label, 'k'));
    var chips = node('div', '', 'ai-chips');
    (items || []).forEach(function (item) { chips.appendChild(node('span', item, 'ai-chip')); });
    if (!items || !items.length) chips.appendChild(node('span', 'Not specified', 'ai-chip'));
    wrap.appendChild(chips);
    return wrap;
  }

  function apiCall(method, path, body, isForm) {
    var options = { method: method };
    if (isForm) {
      options.body = body;
    } else if (body !== undefined) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    return fetch(base + path, options).then(function (response) {
      return response.text().then(function (raw) {
        var parsed = null;
        try { parsed = raw ? JSON.parse(raw) : null; } catch (e) { parsed = null; }
        if (!response.ok) {
          var detail = parsed && parsed.detail;
          var message = (parsed && parsed.error && parsed.error.message)
            || (detail && detail.message)
            || (typeof detail === 'string' ? detail : '')
            || ('That step failed (' + response.status + ').');
          throw new Error(message);
        }
        return parsed;
      });
    });
  }

  // "AI does everything through the shortlist" — reuses the exact
  // same submit/approve/upload/run sequence new-campaign.html's own
  // "Approve and start screening" button already runs (see its comment on
  // that shortcut); the recruiter still makes the one approval click this
  // policy requires, but nothing after that needs manual navigation.
  function runFullScreening(campaign, versionNumber, folderFiles, locationText, statusEl2) {
    var actor = window.__r360ActorName ? window.__r360ActorName() : 'Unknown user';
    statusEl2.textContent = 'Approving the rubric…';
    return apiCall('POST', '/api/campaigns/' + campaign.id + '/rubric/versions/' + versionNumber + '/submit', {})
      .then(function () {
        return apiCall('POST', '/api/campaigns/' + campaign.id + '/rubric/versions/' + versionNumber + '/approve',
          { approved_by: actor });
      })
      .then(function () {
        if (folderFiles && folderFiles.length) {
          statusEl2.textContent = 'Uploading ' + folderFiles.length + ' resume' + (folderFiles.length === 1 ? '' : 's') + '…';
          var form = new FormData();
          Array.prototype.forEach.call(folderFiles, function (file) { form.append('files', file); });
          return apiCall('POST', '/api/campaigns/' + campaign.id + '/batches?name=' +
            encodeURIComponent('Applications for ' + campaign.job_title), form, true);
        }
        statusEl2.textContent = 'Looking for resumes at that location…';
        return apiCall('POST', '/discovery/resolve', { location: locationText, campaign_id: campaign.id })
          .then(function (resolved) {
            var paths = (resolved.files || []).map(function (f) { return f.path; });
            if (!paths.length) throw new Error('No resumes were found at that location.');
            statusEl2.textContent = 'Importing ' + paths.length + ' resume' + (paths.length === 1 ? '' : 's') + '…';
            return apiCall('POST', '/discovery/import', {
              campaign_id: campaign.id,
              resolved_root: resolved.resolved_folder,
              paths: paths,
              name: 'Applications for ' + campaign.job_title,
              created_by: actor,
            });
          });
      })
      .then(function () {
        statusEl2.textContent = 'Scoring every resume against the approved rubric…';
        return apiCall('POST', '/api/campaigns/' + campaign.id + '/evaluations/runs', {
          scoring_mode: 'LLM_ASSISTED',
          notes: 'AI-first campaign: screened immediately after rubric approval.',
        });
      })
      .then(function (run) {
        statusEl2.textContent = 'Done — opening the shortlist…';
        location.href = 'leaderboard.html?run_id=' + encodeURIComponent(run.id);
      });
  }

  function renderReview(body, resumeContext) {
    review.textContent = '';

    if (body.warnings && body.warnings.length) {
      var warn = node('div', '', 'ai-review-warn');
      warn.appendChild(node('div', 'Worth a closer look before you approve:'));
      var ul = document.createElement('ul');
      body.warnings.forEach(function (w) { ul.appendChild(node('li', w)); });
      warn.appendChild(ul);
      review.appendChild(warn);
    }

    review.appendChild(node('h3', 'AI understood'));
    var grid = node('div', '', 'ai-understood');
    var u = body.understood || {};
    grid.appendChild(understoodTile('Role', u.role_title || '—'));
    grid.appendChild(understoodTile(
      'Experience',
      u.min_experience_years != null ? u.min_experience_years + '+ years' : 'Not specified'
    ));
    if (u.location || u.work_arrangement) {
      grid.appendChild(understoodTile('Location', [u.location, u.work_arrangement].filter(Boolean).join(' · ')));
    }
    if (u.vacancies) grid.appendChild(understoodTile('Vacancies', String(u.vacancies)));
    grid.appendChild(chipsRow('Key requirements', u.required_skills));
    if (u.preferred_skills && u.preferred_skills.length) {
      grid.appendChild(chipsRow('Preferred', u.preferred_skills));
    }
    review.appendChild(grid);

    review.appendChild(node('h3', 'Proposed job description'));
    review.appendChild(node('div', body.jd_text || '(no job description was generated)', 'ai-jd'));

    review.appendChild(node('h3', 'Proposed screening rubric'));
    if (body.rubric_criteria && body.rubric_criteria.length) {
      var rubric = node('div', '', 'ai-rubric');
      body.rubric_criteria
        .slice()
        .sort(function (a, b) { return b.weight - a.weight; })
        .forEach(function (c) {
          var row = node('div', '', 'ai-rubric-row');
          var lbl = node('span', c.label, 'lbl');
          lbl.appendChild(node('span', ' · ' + c.category.toLowerCase(), 'cat'));
          row.appendChild(lbl);
          row.appendChild(node('span', Math.round(c.weight) + ' pts', 'wt'));
          rubric.appendChild(row);
        });
      review.appendChild(rubric);
    } else {
      review.appendChild(node('p', 'No rubric was drafted yet — add requirements manually, then build one.'));
    }

    var approve = node('div', '', 'approve');
    var btns = node('div', '', 'btns');

    if (resumeContext && (resumeContext.folderFiles.length || resumeContext.locationText) && body.rubric_version != null) {
      var count = resumeContext.folderFiles.length;
      approve.appendChild(node('p',
        (count ? 'Found ' + count + ' resume' + (count === 1 ? '' : 's') + ' in the folder you chose. '
                : 'A resume location was given. ') +
        'Approving the rubric below will import and score them immediately, then take you straight to ' +
        'the candidate shortlist — same as any other campaign, just without the extra screens.'));
      var runStatus = node('span', '', 'hint');
      var screenBtn = node('button', 'Approve rubric and start screening', 'cta');
      screenBtn.type = 'button';
      screenBtn.onclick = function () {
        screenBtn.disabled = true;
        var original = screenBtn.textContent;
        screenBtn.textContent = 'Working…';
        runFullScreening(body.campaign, body.rubric_version, resumeContext.folderFiles, resumeContext.locationText, runStatus)
          .catch(function (error) {
            screenBtn.disabled = false;
            screenBtn.textContent = original;
            runStatus.textContent = (error && error.message) || 'Something went wrong. Try again.';
          });
      };
      btns.appendChild(screenBtn);
      var manualLink = node('a', 'Or review it manually →', 'ghost');
      var manualHref = 'new-campaign.html?campaign_id=' + encodeURIComponent(body.campaign.id) + '#step3';
      manualLink.href = manualHref;
      // The CVs already chosen above are real File objects — they cannot ride
      // along in a URL. Stash them for the manual review step to pick back up,
      // so the recruiter is never asked to choose the same files twice.
      if (resumeContext.folderFiles.length && window.PendingResumes) {
        manualLink.onclick = function (event) {
          event.preventDefault();
          window.PendingResumes.save(body.campaign.id, resumeContext.folderFiles).then(function () {
            location.href = manualHref;
          });
        };
      }
      btns.appendChild(manualLink);
      btns.appendChild(runStatus);
    } else {
      approve.appendChild(node('p',
        'Nothing is active yet. Review and edit the job description, requirements and weights, ' +
        'then approve the rubric to start screening — same as any other campaign.'));
      var reviewLink = node('a', 'Review & approve →', 'cta');
      reviewLink.href = 'new-campaign.html?campaign_id=' + encodeURIComponent(body.campaign.id) + '#step3';
      btns.appendChild(reviewLink);
      // Land on the same next-step screen a saved-campaign card would resolve
      // to, if the richer resolver is available — same continuation logic the
      // "Your campaigns" list below already uses, not a second copy of it.
      if (window.CampaignSteps && window.CampaignSteps.href) {
        var href = window.CampaignSteps.href(body.campaign, null);
        if (href) reviewLink.href = href;
      }
    }

    var again = node('button', 'Start another', 'ghost');
    again.type = 'button';
    again.onclick = function () {
      review.classList.remove('on');
      textarea.value = '';
      folderInput.value = '';
      if (filesInput) filesInput.value = '';
      locationInput.value = '';
      textarea.focus();
    };
    btns.appendChild(again);
    approve.appendChild(btns);
    review.appendChild(approve);

    review.classList.add('on');
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    clearError();
    review.classList.remove('on');

    var request = textarea.value.trim();
    if (!request) {
      showError('Tell the AI what you need to hire first.');
      return;
    }

    var resumeContext = {
      folderFiles: chosenResumeFiles(),
      locationText: (locationInput && locationInput.value.trim()) || '',
    };

    setBusy(true);
    try {
      var response = await fetch(base + '/api/campaigns/ai-start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: request }),
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) {
        showError(await readErrorDetail(response));
        return;
      }
      var body = await response.json();
      renderReview(body, resumeContext);
    } catch (error) {
      showError('Could not reach the AI assistant. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  });
})();
