"""StoryBridge — local-first runnable accessibility MVP.
Do not expose this demo server to the public Internet (no authentication).
"""
from __future__ import annotations
import base64
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services import ai_engine

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
USER = ROOT / 'user_data'
UPLOADS = USER / 'media'
ANALYSES = USER / 'analyses'
STATIC = ROOT / 'app' / 'static'
for folder in [USER, UPLOADS, ANALYSES]:
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='StoryBridge API', version='1.0.0', description='Local accessibility video prototype')
app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')
lock = threading.RLock()
jobs: dict[str, dict] = {}
live_images: dict[str, str] = {}


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    at: float = Field(ge=0)


class LiveFrame(BaseModel):
    image: str = Field(min_length=20, max_length=2_000_000)
    at: float = Field(ge=0, le=200000)


class YouTubeCreate(BaseModel):
    url: str = Field(min_length=5, max_length=300)


class TimelineImport(BaseModel):
    events: list[dict] = Field(min_length=1, max_length=2000)
    characters: list[dict] = Field(default_factory=list, max_length=100)


class ManualEvent(BaseModel):
    at: float = Field(ge=0)
    description: str = Field(min_length=2, max_length=500)
    narration: str = Field(min_length=2, max_length=300)
    character_ids: list[str] = Field(default_factory=list, max_length=12)


def load_json(path: Path, fallback=None):
    if not path.exists():
        return fallback
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: Path, payload: Any):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def load_meta(video_id: str) -> dict:
    if video_id == 'demo':
        v = load_json(DATA / 'demo_story.json')
        if v:
            return {'id': 'demo', 'title': v['title'], 'platform': 'local', 'duration': v['duration'], 'source': 'demo', 'prepared': True, 'demo': True}
    if not re.fullmatch(r'[a-z0-9\-]{1,60}', video_id):
        raise HTTPException(404, '影片不存在')
    meta = load_json(USER / f'{video_id}.json')
    if not meta:
        raise HTTPException(404, '影片不存在')
    return meta


def timeline(video_id: str) -> dict:
    if video_id == 'demo':
        return load_json(DATA / 'demo_story.json', {})
    m = load_meta(video_id)
    v = load_json(ANALYSES / f'{video_id}.json', {})
    return {'title': m['title'], 'duration': m.get('duration', 0), 'events': v.get('events', []),
            'characters': v.get('characters', []), 'qa': [], 'source': v.get('source', 'empty'),
            'captions': v.get('captions', [])}


def save_timeline(video_id: str, payload: dict):
    if video_id == 'demo':
        raise HTTPException(403, '展示資料不允許覆寫；可上傳自己的影片')
    save_json(ANALYSES / f'{video_id}.json', payload)
    meta = load_meta(video_id)
    meta['prepared'] = bool(payload.get('events'))
    save_json(USER / f'{video_id}.json', meta)


def safe_events(raw: list[dict], limit: float | None = None) -> list[dict]:
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            at = max(0.0, float(item.get('t', 0)))
        except (TypeError, ValueError):
            continue
        if limit is not None and at > limit + 0.001:
            continue
        rows.append({
            'id': str(item.get('id') or uuid.uuid4().hex[:10])[:60],
            't': round(at, 2),
            'description': str(item.get('description', ''))[:500],
            'narration': str(item.get('narration', item.get('description', '')))[:350],
            'characters': item.get('characters', []) if isinstance(item.get('characters', []), list) else [],
            'character_ids': item.get('character_ids', []) if isinstance(item.get('character_ids', []), list) else [],
            'importance': max(1, min(3, int(item.get('importance', 2)))),
            'source': str(item.get('source', 'manual'))[:30],
            'uncertain': bool(item.get('uncertain', False)),
        })
    return sorted(rows, key=lambda e: (e['t'], e['id']))


def visible_characters(v: dict, at: float) -> list[dict]:
    return [c for c in v.get('characters', []) if float(c.get('first_seen', 0)) <= at]


def relevant_events(question: str, events: list[dict]) -> list[dict]:
    """A transparent lexical retrieval fallback, NOT generative AI."""
    q = re.sub(r'[是的誰什麼那個這個剛才剛剛為何怎麼在哪裡有沒有我想知道請問了呢嗎？?\s]', '', question)
    q_chars = set(q)
    if not q_chars:
        return events[-4:]
    scored = []
    for ev in events:
        text = ev.get('description', '') + ev.get('narration', '')
        score = sum((3 if ch in '鑰匙衣服小安小晴' else 1) for ch in q_chars if ch in text)
        if '誰' in question and (ev.get('character_ids') or ev.get('characters')):
            score += 1
        if score:
            scored.append((score, ev['t'], ev))
    scored.sort(key=lambda p: (p[0], p[1]), reverse=True)
    return [p[2] for p in scored[:3]]


def demo_rule_answer(v: dict, q: str, at: float) -> str | None:
    """Rules for the openly labeled handcrafted sample, time-gated."""
    for row in v.get('qa', []):
        if at >= row.get('available_at', 0) and any(word in q for word in row.get('keywords', [])):
            return row['answer']
    return None


@app.get('/')
def homepage():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/health')
def health():
    return {'app': 'StoryBridge', 'version': '1.0.0', 'ai': ai_engine.status(),
            'limitations': {'live_requires_local_ollama': True, 'youtube_video_capture': False,
                            'demo_annotation_is_manual': True}}


@app.get('/api/videos')
def all_videos():
    files = []
    for f in sorted(USER.glob('*.json'), reverse=True):
        v = load_json(f)
        if isinstance(v, dict) and v.get('id'):
            files.append(v)
    return [load_meta('demo'), *files]


@app.get('/api/videos/{video_id}')
def video_info(video_id: str):
    return load_meta(video_id)


@app.get('/api/videos/{video_id}/timeline')
def get_timeline(video_id: str, until: float = 0):
    v = timeline(video_id)
    if until < 0:
        raise HTTPException(400, 'until 不可為負')
    # The server must NOT send future evidence to the interactive Q&A view.
    return {'events': safe_events(v.get('events', []), until),
            'characters': visible_characters(v, until),
            'caption_coverage': bool(v.get('captions')), 'source': v.get('source', 'unknown')}


@app.get('/api/videos/{video_id}/cues')
def get_cues(video_id: str):
    v = timeline(video_id)
    # Scheduling must know future cue positions; do not use these for Q&A.
    return {'cues': [{'id': e['id'], 't': e['t'], 'narration': e['narration'], 'source': e['source']}
                     for e in safe_events(v.get('events', [])) if e['narration']],
            'captions': v.get('captions', []), 'source': v.get('source', 'unknown')}


@app.get('/media/{video_id}')
def serve_video(video_id: str):
    meta = load_meta(video_id)
    if meta['platform'] != 'local':
        raise HTTPException(404, '非本機影片')
    path = ROOT / 'media' / 'demo_story.mp4' if video_id == 'demo' else UPLOADS / f'{video_id}.mp4'
    if not path.exists():
        raise HTTPException(404, '找不到影片檔')
    return FileResponse(path, media_type='video/mp4', filename=path.name, content_disposition_type='inline')


@app.post('/api/videos/upload')
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mp4', '.m4v', '.mov', '.webm'):
        raise HTTPException(400, '請上傳 MP4 / MOV / WebM 影片')
    video_id = uuid.uuid4().hex[:12]
    # File content is not executed, but many browsers cannot play all codecs.
    path = UPLOADS / f'{video_id}.mp4'
    total = 0
    try:
        with path.open('wb') as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise HTTPException(413, '單一檔案上限為 200 MB')
                f.write(chunk)
        if total < 4096:
            raise HTTPException(400, '影片檔太小或無效')
        import cv2
        cap = cv2.VideoCapture(str(path))
        duration = (cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)) if cap.get(cv2.CAP_PROP_FPS) > 0 else 0
        cap.release()
        if duration <= 0:
            raise HTTPException(400, '無法讀取影片；建議轉為 H.264 MP4')
        meta = {'id': video_id, 'title': Path(file.filename or '我的影片').stem[:80], 'platform': 'local',
                'duration': round(duration, 2), 'source': 'user_upload', 'prepared': False, 'demo': False}
        save_json(USER / f'{video_id}.json', meta)
        return meta
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.post('/api/videos/youtube')
def register_youtube(inp: YouTubeCreate):
    match = re.search(r'(?:youtu\.be/|youtube\.com/(?:watch\?[^#]*?v=|embed/|shorts/))([A-Za-z0-9_-]{11})', inp.url)
    if not match:
        raise HTTPException(400, '請輸入有效的 YouTube 影片網址')
    youtube_id = match.group(1)
    video_id = uuid.uuid4().hex[:12]
    meta = {'id': video_id, 'youtube_id': youtube_id, 'platform': 'youtube', 'title': f'YouTube · {youtube_id}',
            'duration': 0, 'prepared': False, 'source': 'youtube_player_sync_only', 'demo': False}
    save_json(USER / f'{video_id}.json', meta)
    return meta


@app.post('/api/videos/{video_id}/timeline/import')
def import_timeline(video_id: str, inp: TimelineImport):
    m = load_meta(video_id)
    if video_id == 'demo':
        raise HTTPException(403, '不能覆寫展示資料')
    events = safe_events(inp.events)
    chars = []
    for c in inp.characters:
        if isinstance(c, dict):
            chars.append({'id': str(c.get('id', ''))[:40], 'name': str(c.get('name', ''))[:70],
                          'description': str(c.get('description', ''))[:400], 'first_seen': max(0, float(c.get('first_seen', 0)))})
    payload = {'events': events, 'characters': chars, 'source': 'user_imported_annotations', 'captions': []}
    save_timeline(video_id, payload)
    return {'count': len(events), 'characters': len(chars), 'notice': '這些是使用者匯入的資料，非AI自動辨識'}


@app.post('/api/videos/{video_id}/events')
def manual_event(video_id: str, inp: ManualEvent):
    load_meta(video_id)
    v = timeline(video_id)
    event = {'id': uuid.uuid4().hex[:10], 't': round(inp.at, 2), 'description': inp.description,
             'narration': inp.narration, 'character_ids': inp.character_ids, 'characters': [],
             'importance': 2, 'source': 'human_annotation', 'uncertain': False}
    v['events'] = safe_events([*v.get('events', []), event])
    v['source'] = 'human_annotation'
    save_timeline(video_id, v)
    return {'event': event}


def prepare_worker(job_id: str, video_id: str, every: float):
    import cv2
    cap = None
    try:
        meta = load_meta(video_id)
        path = UPLOADS / f'{video_id}.mp4'
        cap = cv2.VideoCapture(str(path))
        duration = meta['duration']
        timestamps = [round(t, 2) for t in _frange(1, min(duration, 600), every)][:80]
        if not timestamps:
            timestamps = [0.0]
        rows = []
        prev = None
        for i, sec in enumerate(timestamps):
            with lock:
                jobs[job_id].update(progress=i, total=len(timestamps), message=f'分析 {i+1}/{len(timestamps)} 張畫面')
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            encoded = ai_engine.b64_from_cv_frame(frame)
            obs = ai_engine.analyze_frame(encoded, time_sec=sec, recent_context=rows, previous_b64=prev)
            prev = encoded
            rows.append({'id': uuid.uuid4().hex[:10], 't': sec, **obs, 'source': 'ollama_visual',
                         'character_ids': []})
        if not rows:
            raise RuntimeError('無法讀取任何影格')
        v = {'events': safe_events(rows), 'characters': [], 'source': 'ollama_visual', 'captions': []}
        save_timeline(video_id, v)
        with lock:
            jobs[job_id].update(state='done', progress=len(timestamps), total=len(timestamps), message=f'完成 {len(rows)} 個事件')
    except Exception as e:
        with lock:
            jobs[job_id].update(state='error', message=str(e)[:500])
    finally:
        if cap is not None:
            cap.release()


def _frange(start, end, step):
    while start < end:
        yield start
        start += step


@app.post('/api/videos/{video_id}/prepare')
def prepare(video_id: str, every: float = 6):
    meta = load_meta(video_id)
    if meta['platform'] != 'local' or video_id == 'demo':
        raise HTTPException(400, '只支援自行上傳的本機影片')
    if not 2 <= every <= 30:
        raise HTTPException(400, '抽幀秒數必須介於 2 和 30')
    if not ai_engine.status()['vision_ready']:
        raise HTTPException(503, '請先啟動 Ollama 並下載設定的多模態模型')
    job_id = uuid.uuid4().hex[:12]
    with lock:
        jobs[job_id] = {'state': 'running', 'progress': 0, 'total': 0, 'message': '準備分析'}
    threading.Thread(target=prepare_worker, args=(job_id, video_id, every), daemon=True).start()
    return {'job_id': job_id}


@app.get('/api/jobs/{job_id}')
def job_progress(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, '不存在的工作')
        return jobs[job_id].copy()


@app.post('/api/videos/{video_id}/live')
def analyze_live(video_id: str, inp: LiveFrame):
    m = load_meta(video_id)
    if m['platform'] != 'local':
        raise HTTPException(400, 'YouTube 播放器無法供應可分析的影格；請用已授權的本機影片')
    if not ai_engine.status()['vision_ready']:
        raise HTTPException(503, 'Live AI 尚未就緒。請先安裝 Ollama 視覺模型；展示影片的口述來自人工標註，不是假造的 Live AI。')
    try:
        raw = base64.b64decode(inp.image, validate=True)
        if len(raw) > 1_400_000:
            raise ValueError('影像超過上限')
        from PIL import Image
        from io import BytesIO
        im = Image.open(BytesIO(raw))
        im.verify()
    except Exception:
        raise HTTPException(400, '無效的 JPEG 影像')
    v = timeline(video_id)
    evidence = safe_events(v.get('events', []), inp.at)
    # Previous frame only from same video. Global simple state: single-user localhost MVP.
    prev = live_images.get(video_id)
    observation = ai_engine.analyze_frame(inp.image, time_sec=inp.at, recent_context=evidence, previous_b64=prev)
    live_images[video_id] = inp.image
    event = {'id': uuid.uuid4().hex[:10], 't': round(inp.at, 2), **observation,
             'character_ids': [], 'source': 'ollama_live_visual'}
    v['events'] = safe_events([*v.get('events', []), event])
    v['source'] = 'ollama_live_visual'
    save_timeline(video_id, v) if video_id != 'demo' else None
    return {'event': event, 'notice': '這是模型根據取樣影格推測的觀察，非已驗證的角色身分'}


@app.post('/api/videos/{video_id}/qa')
def ask_video(video_id: str, inp: Question):
    v = timeline(video_id)
    events = safe_events(v.get('events', []), inp.at)
    if not events:
        return {'answer': '目前還沒有足夠的已觀看資訊回答這個問題。', 'source': 'no_evidence', 'evidence': []}
    if video_id == 'demo':
        ans = demo_rule_answer(v, inp.question, inp.at)
        if ans:
            return {'answer': ans, 'source': 'demo_authored_qa', 'evidence': [e['t'] for e in relevant_events(inp.question, events)[:2]]}
    picked = relevant_events(inp.question, events)
    st = ai_engine.status()
    if st['text_ready']:
        try:
            response = ai_engine.answer_grounded(inp.question, events, visible_characters(v, inp.at), inp.at)
            return {'answer': response, 'source': 'ollama_time_filtered', 'evidence': [e['t'] for e in picked]}
        except Exception:
            pass
    if picked:
        e = picked[0]
        return {'answer': f'依目前已記錄的畫面，在 {int(e["t"] // 60):02d}:{int(e["t"] % 60):02d} 左右：{e["description"]}（這是事件檢索，尚未啟用生成式問答。）',
                'source': 'keyword_retrieval', 'evidence': [x['t'] for x in picked]}
    return {'answer': '目前已觀看的畫面記錄不足以確認這個問題。', 'source': 'no_match', 'evidence': []}


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    # Keep response helpful while not leaking filesystem paths or internal tracebacks.
    return JSONResponse(status_code=500, content={'detail': f'系統錯誤：{type(exc).__name__}'})
