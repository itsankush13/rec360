(function () {
  var list = document.getElementById('campaign-list');
  if (!list) return;
  var message = document.getElementById('campaign-list-status');
  var filterBox = document.getElementById('campaign-filter');
  var base = (localStorage.getItem('recruitment360.apiBase') || (/^(localhost|127.0.0.1)$/.test(location.hostname) ? 'http://localhost:8000' : location.origin)).replace(/\/$/, '');
  var allCampaigns = [];
  function node(tag, text, cls) {
    var el = document.createElement(tag);
    el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  async function read(path) {
    var response = await fetch(base + path, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('Campaign could not be loaded');
    return response.json();
  }
  async function stage(card, campaign) {
    var action = card.querySelector('.campaign-resume');
    action.textContent = 'Checking saved stage…';
    try {
      var result = await window.CampaignSteps.resolve(campaign, read);
      var link = node('a', result.label, 'cta campaign-resume');
      link.href = result.href;
      link.setAttribute('aria-label', result.label + ' — ' + (campaign.job_title || 'Untitled role'));
      action.replaceWith(link);
    } catch (error) {
      var retry = node('button', 'Could not load stage · Retry', 'ghost campaign-resume');
      retry.type = 'button';
      retry.onclick = function () { stage(card, campaign); };
      action.replaceWith(retry);
    }
  }
  function matches(campaign, term) {
    if (!term) return true;
    var haystack = [campaign.name, campaign.job_title, campaign.short_id, campaign.hiring_manager, campaign.recruiter, campaign.business_unit]
      .filter(Boolean).join(' ').toLowerCase();
    return haystack.indexOf(term.toLowerCase()) !== -1;
  }
  async function render(campaigns, totalCount) {
    list.textContent = '';
    if (!campaigns.length) {
      message.textContent = totalCount ? 'No campaigns match "' + filterBox.value + '".' : 'No campaigns yet. Create your first campaign above.';
      return;
    }
    message.textContent = campaigns.length === totalCount
      ? campaigns.length + ' saved campaigns'
      : campaigns.length + ' of ' + totalCount + ' campaigns shown';
    var labels = window.campaignOptions(campaigns);
    var cards = campaigns.map(function (campaign, index) {
      var card = node('article', '', 'saved-campaign');
      card.dataset.campaignId = campaign.id;
      card.appendChild(node('h3', labels[index].label));
      card.appendChild(node('p', (campaign.short_id ? campaign.short_id + ' · ' : '') +
        (campaign.vacancies || 1) + ((campaign.vacancies || 1) === 1 ? ' vacancy' : ' vacancies') + (campaign.hiring_manager ? ' · ' + campaign.hiring_manager : '')));
      card.appendChild(node('span', 'Checking saved stage…', 'campaign-resume'));
      list.appendChild(card);
      return card;
    });
    // Bound concurrent detail reads even when there are many campaigns.
    var cursor = 0;
    await Promise.all(Array.from({ length: Math.min(4, campaigns.length) }, async function () {
      while (cursor < campaigns.length) {
        var index = cursor++;
        await stage(cards[index], campaigns[index]);
      }
    }));
  }
  async function load() {
    message.textContent = 'Loading campaigns…';
    list.textContent = '';
    try {
      allCampaigns = await read('/api/campaigns');
      await render(allCampaigns, allCampaigns.length);
    } catch (error) {
      message.textContent = 'Campaigns could not be loaded. Your saved work has not changed. ';
      var retry = node('button', 'Retry', 'ghost');
      retry.type = 'button';
      retry.onclick = load;
      message.appendChild(retry);
    }
  }
  if (filterBox) {
    var debounceHandle;
    filterBox.addEventListener('input', function () {
      clearTimeout(debounceHandle);
      debounceHandle = setTimeout(function () {
        var term = filterBox.value.trim();
        render(allCampaigns.filter(function (c) { return matches(c, term); }), allCampaigns.length);
      }, 150);
    });
  }
  load();
})();
