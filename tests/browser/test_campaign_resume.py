"""Exercise the shipped resume rule against saved API records."""
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / 'web/assets/app.js'


def resolve(campaign, records):
    script = f"""
global.window = global;
// X32: app.js's B22 portal gate runs document.documentElement.classList.add
// at import, before this test's own resume logic runs. Stubbed so this stays
// a real test of that logic without a browser, not a crash on an unrelated line.
global.document = {{querySelector:()=>null,querySelectorAll:()=>[],addEventListener:()=>{{}},readyState:'complete',documentElement:{{classList:{{add:()=>{{}},remove:()=>{{}}}}}}}};
global.localStorage = {{getItem:()=>null,setItem:()=>{{}}}};
global.sessionStorage = localStorage;
global.location = {{pathname:'/test.html',protocol:'http:',search:'',replace:()=>{{}}}};
global.navigator = {{}};
require({json.dumps(APP.as_posix())});
CampaignSteps.resolve({json.dumps(campaign)}, async path => {{
  const records = {json.dumps(records)};
  if (!(path in records)) throw Error('unexpected request: ' + path);
  return records[path];
}}).then(result => console.log(JSON.stringify(result)));
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_saved_description_without_extraction_resumes_description():
    result = resolve({'id':'a','status':'DRAFT','job_title':'Welder','job_description':'Weld pipes'},
                     {'/api/campaigns/a/requirements': []})
    assert result['step'] == 'jd'
    assert result['href'] == 'new-campaign.html?campaign_id=a#jd'


def test_extracted_description_advances_to_rules():
    result = resolve({'id':'a','status':'DRAFT','job_title':'Welder','job_description':'Weld pipes'},
                     {'/api/campaigns/a/requirements': [{'id':'r'}]})
    assert result['step'] == 'requirements'
    assert result['label'] == 'Review the scoring rules'


def test_approved_campaign_advances_to_upload():
    result = resolve({'id':'a','status':'APPROVED'}, {'/api/campaigns/a/evaluations/runs': []})
    assert result['step'] == 'cvs'


def test_completed_assessment_opens_its_results():
    result = resolve({'id':'a','status':'REVIEW'}, {'/api/campaigns/a/evaluations/runs': [
        {'id':'old','status':'COMPLETED','created_at':'2026-09-10'},
        {'id':'new','status':'COMPLETED','created_at':'2026-09-12'}]})
    assert result['href'] == 'leaderboard.html?run_id=new'


def test_unfinished_assessment_has_a_campaign_destination():
    result = resolve({'id':'a','status':'PROCESSING'}, {'/api/campaigns/a/evaluations/runs': []})
    assert result['step'] == 'assess'
    assert 'campaign=a' in result['href']
