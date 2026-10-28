"""Ollama vision + grounded question answering.
No cloud calls: connects ONLY to the configurable local Ollama instance.
"""
import base64
import json
import os
import re
from typing import Any
import requests

OLLAMA_URL = os.getenv('STORYBRIDGE_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
VISION_MODEL = os.getenv('STORYBRIDGE_VISION_MODEL', 'qwen3-vl:4b-instruct')
TEXT_MODEL = os.getenv('STORYBRIDGE_TEXT_MODEL', VISION_MODEL)


def status() -> dict:
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=2)
        r.raise_for_status()
        names = [m.get('name', '') for m in r.json().get('models', [])]
        def found(target):
            return target in names or any(n.split(':')[0] == target.split(':')[0] and target.endswith(':latest') for n in names)
        return {'reachable': True, 'models': names, 'vision_model': VISION_MODEL, 'vision_ready': found(VISION_MODEL), 'text_model': TEXT_MODEL, 'text_ready': found(TEXT_MODEL)}
    except (requests.RequestException, ValueError):
        return {'reachable': False, 'models': [], 'vision_model': VISION_MODEL, 'vision_ready': False, 'text_model': TEXT_MODEL, 'text_ready': False}


def _generate(prompt: str, images: list[str] | None = None, *, as_json: bool = True, model: str | None = None, timeout: int = 180) -> str:
    payload = {'model': model or VISION_MODEL, 'prompt': prompt, 'stream': False,
               'options': {'temperature': 0.1, 'num_predict': 350}}
    if images:
        payload['images'] = images
    if as_json:
        payload['format'] = 'json'
    try:
        resp = requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=timeout)
        resp.raise_for_status()
        return str(resp.json().get('response', '')).strip()
    except requests.RequestException as e:
        raise RuntimeError(f'本機 AI 無法完成推論：{e}') from e


def parse_json(reply: str) -> dict:
    try:
        v = json.loads(reply)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r'\{.*\}', reply or '', re.S)
        if not match:
            raise ValueError('模型回傳不是 JSON；請重試')
        v = json.loads(match.group())
    if not isinstance(v, dict):
        raise ValueError('模型回傳的 JSON 不是物件')
    return v


def analyze_frame(image_b64: str, *, time_sec: float, recent_context: list[dict], previous_b64: str | None = None) -> dict:
    recent_text = json.dumps([{'t': e.get('t'), 'description': e.get('description'), 'characters': e.get('characters', [])} for e in recent_context[-5:]], ensure_ascii=False)
    prompt = f'''你是一名視障觀影輔助系統的影像觀察員。時間點 {time_sec:.1f} 秒。
已確認的先前觀察（可能不完整）：{recent_text}
{"圖片1是前一時刻，圖片2是目前影格；只根據可見差異描述動作。" if previous_b64 else "這是目前唯一影格；不要把單張靜態畫面說成看見了連續動作。"}
請只根據圖片可見資訊產生繁體中文 JSON，格式：
{{"description":"客觀、簡短的當前畫面描述，25至55字", "narration":"適合口述的15至40字句子", "characters":[{{"label":"人物1或已證實的名字", "appearance":"眼前可見特徵", "identity_confidence":0.0}}], "importance":1, "uncertain":false}}
importance 範圍 1~3（3最關鍵）。不能憑服裝判定同一個角色、不能猜名字、心理狀態或看不到的事件；如無法確認人物身分，請使用「一名男子／女子／人物」等描述，confidence 不超過0.5。不要劇透，也不要聲稱聽到未提供的音訊。JSON 之外不要補充文字。'''
    imgs = [previous_b64, image_b64] if previous_b64 else [image_b64]
    v = parse_json(_generate(prompt, imgs))
    desc = str(v.get('description') or '').strip()[:350]
    narr = str(v.get('narration') or desc).strip()[:160]
    if not desc and not narr:
        raise ValueError('模型未輸出描述')
    characters = v.get('characters', [])
    if not isinstance(characters, list):
        characters = []
    return {'description': desc or narr, 'narration': narr or desc,
            'characters': [{'label': str(p.get('label', '未知人物'))[:40], 'appearance': str(p.get('appearance', ''))[:120], 'identity_confidence': min(1, max(0, float(p.get('identity_confidence', 0))))} for p in characters[:6] if isinstance(p, dict)],
            'importance': max(1, min(3, int(v.get('importance', 1)))), 'uncertain': bool(v.get('uncertain', False))}


def answer_grounded(question: str, evidence: list[dict], characters: list[dict], now: float) -> str:
    """The evidence array is already time-filtered by the caller."""
    if not evidence:
        return '目前還沒有足夠的已觀看畫面資訊，可以稍後再問我。'
    context = json.dumps([{'t': e['t'], 'description': e.get('description', ''), 'characters': e.get('characters', [])} for e in evidence[-24:]], ensure_ascii=False)
    profile = json.dumps([{'id': c.get('id'), 'name': c.get('name'), 'description': c.get('description')} for c in characters if c.get('first_seen', 0) <= now], ensure_ascii=False)
    prompt = f'''你是視障者的影片問答助手。現在播放到 {now:.1f} 秒，絕對不能引用未播放情節。
你唯一可用的證據如下（可能來自人工示範標註或AI觀察，都可能不完整）：
事件：{context}
人物：{profile}
使用者問題：{question[:500]}
請只回答有明確證據支持的事實；未能證實人物身分、劇情因果或未來發展時，明確說「目前無法確認」。簡短繁體中文，1至2句，不要加上證據中沒有的情節。'''
    return _generate(prompt, as_json=False, model=TEXT_MODEL, timeout=100)[:550]


def b64_from_cv_frame(frame: Any, max_width: int = 720) -> str:
    import cv2
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, round(h * max_width / w)))
    ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 76])
    if not ok:
        raise RuntimeError('影格 JPEG 編碼失敗')
    return base64.b64encode(buf.tobytes()).decode('ascii')
