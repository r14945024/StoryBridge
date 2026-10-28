import io
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_and_demo_video():
    r = client.get('/')
    assert r.status_code == 200 and 'StoryBridge' in r.text
    demos = client.get('/api/videos').json()
    assert demos[0]['id'] == 'demo'
    r = client.get('/media/demo')
    assert r.status_code == 200 and len(r.content) > 100000


def test_playback_timeline_gates_future_events():
    early = client.get('/api/videos/demo/timeline?until=5').json()
    assert [e['id'] for e in early['events']] == ['e01']
    assert len(early['characters']) == 2
    later = client.get('/api/videos/demo/timeline?until=29').json()
    assert [e['id'] for e in later['events']] == ['e01', 'e02', 'e03', 'e04']
    assert not any(e['id'] == 'e05' for e in later['events'])


def test_qa_not_spoiling():
    early = client.post('/api/videos/demo/qa', json={'question':'誰拿走鑰匙？','at':4}).json()
    assert '小安拿走' not in early['answer']
    later = client.post('/api/videos/demo/qa', json={'question':'誰拿走鑰匙？','at':12}).json()
    assert '小安' in later['answer'] and later['source'] == 'demo_authored_qa'
    before_change = client.post('/api/videos/demo/qa', json={'question':'穿藍色外套的是同一人嗎？','at':10}).json()
    assert '同一角色' not in before_change['answer'] and '人工標註的真值' not in before_change['answer']
    after_change = client.post('/api/videos/demo/qa', json={'question':'穿藍色外套的是同一人嗎？','at':28}).json()
    assert '藍色外套' in after_change['answer']


def test_cues_and_characters():
    cues = client.get('/api/videos/demo/cues').json()['cues']
    assert len(cues)==8
    assert cues[0]['t']==1


def test_upload_and_annotation(tmp_path):
    # Use a copy of the demo file to verify the actual video upload pipeline.
    from app.main import ROOT, UPLOADS, USER, ANALYSES
    src = (ROOT/'media'/'demo_story.mp4').read_bytes()
    r = client.post('/api/videos/upload',files={'file':('short.mp4',io.BytesIO(src),'video/mp4')})
    assert r.status_code==200,r.text
    data=r.json()
    id=data['id']
    try:
        assert data['duration']>60
        r=client.post(f'/api/videos/{id}/events',json={'at':3,'description':'角色開門。','narration':'一名人物打開門。'})
        assert r.status_code==200,r.text
        events=client.get(f'/api/videos/{id}/timeline?until=3.1').json()['events']
        assert len(events)==1 and events[0]['source']=='human_annotation'
        r=client.post(f'/api/videos/{id}/timeline/import',json={'events':[{'t':2,'description':'人物坐在桌子旁。','narration':'一人坐在桌旁。'}],'characters':[{'id':'C01','name':'甲','first_seen':0}]})
        assert r.status_code==200
        assert client.get(f'/api/videos/{id}/timeline?until=4').json()['characters'][0]['name']=='甲'
    finally:
        (UPLOADS/f'{id}.mp4').unlink(missing_ok=True)
        (USER/f'{id}.json').unlink(missing_ok=True)
        (ANALYSES/f'{id}.json').unlink(missing_ok=True)


def test_youtube_sync_not_frame_grab():
    from app.main import USER, ANALYSES
    r=client.post('/api/videos/youtube',json={'url':'https://www.youtube.com/watch?v=jfKfPfyJRdk'})
    assert r.status_code==200
    d=r.json()
    try:
        assert d['youtube_id']=='jfKfPfyJRdk'
        assert client.post(f'/api/videos/{d["id"]}/live',json={'at':0,'image':'a'*50}).status_code==400
    finally:
        (USER/f'{d["id"]}.json').unlink(missing_ok=True)
        (ANALYSES/f'{d["id"]}.json').unlink(missing_ok=True)


def test_model_not_implicitly_available():
    r=client.get('/api/health')
    assert r.status_code==200
    result=r.json()
    assert result['limitations']['demo_annotation_is_manual'] is True
    assert result['limitations']['youtube_video_capture'] is False
