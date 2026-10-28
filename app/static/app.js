'use strict';
const el = id => document.getElementById(id);
const state = {
  catalog:[], meta:null, mode:'prepared', yt:null, ytReady:false, ytApiRequested:false,
  cues:[], captions:[], visibleEvents:[], characters:[], announced:new Set(),
  voiceEnabled:true, subtitlesEnabled:true, isSeeking:false, playing:false,
  loadingVideo:false, inLiveCall:false, lastLiveTime:-100, lastEventRequest:0,
  lastCue:-1, lastTime:0, ai:null, qaBusy:false, lastNarratedText:'',
};
const video = el('videoPlayer');
const $ = el;
function toast(message,type='info'){
  const node=document.createElement('div');node.className=`toast ${type}`;node.textContent=message;
  $('toastStack').append(node);setTimeout(()=>node.remove(),4800);
}
async function request(url, options={}){
  const r=await fetch(url,options);let data;
  try{data=await r.json()}catch{data={detail:`伺服器回傳 ${r.status}`}}
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${r.status}`);
  return data;
}
function apiPost(path, payload){return request(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})}
function fmt(t){if(!isFinite(t))return '00:00';const n=Math.max(0,Math.floor(t));return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
function currentTime(){if(state.meta?.platform==='youtube'&&state.ytReady){try{return state.yt.getCurrentTime()||0}catch{return 0}}return video.currentTime||0}
function duration(){if(state.meta?.platform==='youtube'&&state.ytReady){try{return state.yt.getDuration()||0}catch{return 0}}return isFinite(video.duration)?video.duration:(state.meta?.duration||0)}
function isPlaying(){if(state.meta?.platform==='youtube'&&state.ytReady){try{return state.yt.getPlayerState()===1}catch{return false}}return !video.paused&&!video.ended}
function setPause(){if(state.meta?.platform==='youtube'){if(state.ytReady)state.yt.pauseVideo()}else video.pause();speechSynthesis.cancel();}
async function togglePlay(){if(!state.meta)return;if(isPlaying()){setPause();return}if(state.meta.platform==='youtube'){if(!state.ytReady)return toast('YouTube 播放器尚未就緒','error');state.yt.playVideo()}else{try{await video.play()}catch(e){toast('瀏覽器無法播放此影片：請使用 H.264 MP4。','error')}}}
function seekTo(t){let target=Math.max(0,Math.min(t,duration()||t));speechSynthesis.cancel();if(state.meta.platform==='youtube'){if(state.ytReady)state.yt.seekTo(target,true)}else video.currentTime=target;
  state.announced=new Set(state.cues.filter(c=>c.t<target-0.7).map(c=>c.id));state.lastTime=target;state.lastCue=-1;state.lastLiveTime=target-8;setNarration('已跳轉至 '+fmt(target)+'，等待下一個有效口述片段。','重新同步');updateClock();fetchMemory(true);
}
function updateClock(){const at=currentTime();const dur=duration();$('currentTime').textContent=fmt(at);$('duration').textContent=fmt(dur);$('seekBar').max=Math.max(1,dur);if(!state.isSeeking)$('seekBar').value=Math.min(dur||0,at);$('seekBar').style.setProperty('--progress',`${dur>0?(at/dur)*100:0}%`);$('playPause').textContent=isPlaying()?'Ⅱ':'▶';$('playPause').setAttribute('aria-label',isPlaying()?'暫停':'播放');}
function setNarration(text,status='口述已就緒'){
  $('currentNarration').textContent=text;$('narrationStatus').textContent=status;
  $('narrationOverlay').textContent=text;$('narrationOverlay').hidden=!state.subtitlesEnabled||!text;
}
function speech(text){if(!state.voiceEnabled||!('speechSynthesis' in window))return;
  try{speechSynthesis.cancel();let utterance=new SpeechSynthesisUtterance(text);utterance.lang='zh-TW';utterance.rate=Number($('speechRate').value);utterance.volume=1;
    const voices=speechSynthesis.getVoices();const v=voices.find(x=>x.lang.toLowerCase()==='zh-tw')||voices.find(x=>x.lang.startsWith('zh'));if(v)utterance.voice=v;
    utterance.onerror=e=>{if(e.error!=='interrupted'&&e.error!=='canceled')toast('語音合成未成功；可先看文字口述','error')};speechSynthesis.speak(utterance);
  }catch(e){toast('瀏覽器尚未支援中文語音合成','error')}
}
function useNarration(now){if(!isPlaying()||!state.voiceEnabled)return;
  if(Math.abs(now-state.lastTime)>5){state.announced=new Set(state.cues.filter(c=>c.t<now-0.7).map(c=>c.id));}
  const cue=state.cues.find(c=>!state.announced.has(c.id)&&now>=c.t&&now<=c.t+3.2);
  if(!cue)return;
  state.announced.add(cue.id);
  const dialogue=state.captions.some(c=>now>=c.start-0.25&&now<=c.end+0.25);
  if(dialogue){setNarration('偵測到字幕對白區間，已略過本次口述以減少干擾。','避開對白');return}
  state.lastCue=cue.t;state.lastNarratedText=cue.narration;setNarration(cue.narration,'正在口述 · '+fmt(cue.t));speech(cue.narration);
}
function li(parent,className,text){const n=document.createElement('div');n.className=className;n.textContent=text;parent.append(n);return n}
function renderEvents(){
  let list=$('eventList');list.replaceChildren();let events=state.visibleEvents;$('eventCount').textContent=`${events.length} 個事件`;
  if(!events.length){li(list,'empty-state','尚無已觀看的事件。播放後將隨時間顯示。');return}
  for(const ev of events.slice(-9).reverse()){
    const row=li(list,'event-row','');li(row,'event-time',fmt(ev.t));const right=li(row,'event-copy','');li(right,'event-desc',ev.description||ev.narration);li(right,'event-source',ev.source.startsWith('human')?'人工標註':ev.source.includes('ollama')?'AI 影格觀察 · 可能有誤':'匯入事件');
  }
}
function renderCharacters(){const host=$('characterList');host.replaceChildren();if(!state.characters.length){li(host,'empty-state','尚未建立確定的角色身分；Live AI 的人物描述不等於身分確認。');return}
  for(const [i,c] of state.characters.entries()){
    let card=li(host,'character-item','');li(card,'character-avatar',i%2?'◉':'◈');let txt=li(card,'character-copy','');li(txt,'',''+(c.name||c.id||'未知角色')).className='character-name';txt.lastChild.style.fontWeight='700';li(txt,'',c.description||'尚無說明');
  }
}
let memoryRequestedAt=-10;let memoryPending=false;
async function fetchMemory(force=false){if(!state.meta||memoryPending)return;const now=currentTime();if(!force&&Math.abs(now-memoryRequestedAt)<1.5)return;memoryRequestedAt=now;memoryPending=true;
  const id=state.meta.id;
  try{const data=await request(`/api/videos/${id}/timeline?until=${encodeURIComponent(now)}`);if(state.meta?.id!==id)return;state.visibleEvents=data.events||[];state.characters=data.characters||[];renderEvents();renderCharacters()}
  catch(e){console.warn('事件清單讀取失敗',e)}finally{memoryPending=false}
}
function paintLibrary(){let host=$('videoList');host.replaceChildren();$('libraryCount').textContent=state.catalog.length;
  for(let v of state.catalog){let b=document.createElement('button');b.type='button';b.className='video-choice'+(state.meta?.id===v.id?' active':'');b.setAttribute('aria-label','開啟 '+v.title);let icon=li(b,'video-icon',v.platform==='youtube'?'▶':v.demo?'✦':'▸');let container=li(b,'','');li(container,'video-title',v.title);container.lastChild.style.fontWeight='600';li(container,'video-meta',v.demo?'人工標註範例':v.platform==='youtube'?'僅播放同步':v.prepared?'已建立分析資料':'等待 AI 分析');b.onclick=()=>selectVideo(v.id);host.append(b)}
}
function clearYoutube(){
  if(state.yt){try{state.yt.destroy()}catch{}}
  state.yt=null;state.ytReady=false;
  // The YouTube API replaces the original DIV with an IFRAME. Always rebuild it.
  const existing=document.getElementById('youtubePlayer');if(existing)existing.remove();
  const holder=document.createElement('div');holder.id='youtubePlayer';holder.hidden=true;
  $('videoStage').insertBefore(holder,$('videoPlaceholder'));
}
function ensureYoutube(callback){if(window.YT?.Player){callback();return}if(!state.ytApiRequested){state.ytApiRequested=true;let s=document.createElement('script');s.src='https://www.youtube.com/iframe_api';s.async=true;document.head.append(s)}window.onYouTubeIframeAPIReady=()=>callback()}
function mountYouTube(videoId){video.hidden=true;$('youtubePlayer').hidden=false;ensureYoutube(()=>{
  if(state.meta?.youtube_id!==videoId)return;
  state.yt=new window.YT.Player('youtubePlayer',{height:'100%',width:'100%',videoId,playerVars:{playsinline:1,rel:0,origin:location.origin},events:{onReady:()=>{state.ytReady=true;updateClock()},onStateChange:()=>updateClock(),onError:()=>toast('YouTube 播放錯誤；部分影片禁止嵌入','error')}})
})}
async function selectVideo(id){
  try{
    setPause();clearYoutube();state.loadingVideo=true;const data=await request(`/api/videos/${id}`);state.meta=data;state.visibleEvents=[];state.characters=[];state.cues=[];state.captions=[];state.announced.clear();state.lastLiveTime=-100;state.lastEventRequest=0;state.lastTime=0;memoryRequestedAt=-10;
    $('demoBadge').hidden=!data.demo;$('videoSource').textContent=data.platform==='youtube'?'YOUTUBE SYNC':'LOCAL VIDEO';
    if(data.platform==='youtube'){mountYouTube(data.youtube_id)}else{video.hidden=false;video.src=`/media/${id}`;video.load()}
    state.mode=data.prepared?'prepared':(data.platform==='youtube'?'prepared':'live');paintMode();
    const cues=await request(`/api/videos/${id}/cues`);state.cues=cues.cues||[];state.captions=cues.captions||[];
    await fetchMemory(true);paintLibrary();updateClock();
    if(data.demo)setNarration('這部展示影片的人物與劇情由人工標註，請按播放鍵開始體驗。','展示模式 · 非AI自動辨識');
    else if(!data.prepared)setNarration('這部影片尚無口述資料。可啟用 Live AI，或先進行整部影片分析。','等待分析');
    else setNarration('已載入分析時間軸，按播放鍵開始同步口述。','口述資料就緒');
  }catch(e){toast(e.message,'error')}finally{state.loadingVideo=false}
}
function paintMode(){
  const isLive=state.mode==='live';$('preparedMode').classList.toggle('selected',!isLive);$('liveMode').classList.toggle('selected',isLive);$('preparedMode').querySelector('.mode-check').textContent=isLive?'':'✓';$('liveMode').querySelector('.mode-check').textContent=isLive?'✓':'';
  $('liveMode').disabled=state.meta?.platform==='youtube';$('modeDetail').textContent=isLive?'LIVE ANALYSIS':'PREPARED';
  $('modeNotice').textContent=isLive?'Live 模式每約 8 秒將目前播放畫面送往本機 Ollama 進行視覺分析；需要安裝並啟動視覺模型。生成結果可能有誤，人物身分不會被自動視為已確認。':state.meta?.demo?'目前是人工標註的可驗證示範；不代表已成功自動辨識人物。':state.meta?.platform==='youtube'?'YouTube 僅支援官方播放器進度同步。無法直接取得其影片畫面；請匯入自己有權使用的影片口述時間軸。':'使用已分析的口述時間軸；若尚無資料，可按「使用本機 AI 分析整部影片」。';
  $('prepareBtn').disabled=state.meta?.platform!=='local'||state.meta?.demo||!state.ai?.vision_ready;
  $('manualBtn').disabled=!state.meta||state.meta.demo;
}
async function refreshAI(){try{const h=await request('/api/health');state.ai=h.ai;const ready=state.ai.vision_ready;$('aiBadge').className='status-badge'+(ready?'':' disconnected');$('aiBadge').textContent=ready?'● 本機 AI 已連線':'● AI 尚未連線';$('modelSide').textContent=ready?'Ollama 視覺模型已就緒':'可體驗示範 · 需安裝 Ollama';document.querySelector('.live-dot').classList.toggle('active',ready);paintMode()}catch(e){$('aiBadge').textContent='● 後端無法連線';toast(e.message,'error')}}
function setMode(mode){if(mode==='live'&&state.meta?.platform==='youtube'){toast('YouTube 無法直接擷取畫面進行 Live 分析','error');return}
  if(mode==='live'&&!state.ai?.vision_ready)toast('Live AI 需要 Ollama + 視覺模型；目前可先操作人工標註示範。','error');
  state.mode=mode;state.lastLiveTime=-100;paintMode();
}
async function tick(){if(state.loadingVideo||!state.meta)return;updateClock();const now=currentTime();if(now<state.lastTime-2.0||now>state.lastTime+12){state.announced=new Set(state.cues.filter(c=>c.t<now-0.7).map(c=>c.id));}
  if(isPlaying()){if(state.mode==='prepared')useNarration(now);else await maybeLive(now)}
  state.lastTime=now;fetchMemory();
}
async function maybeLive(now){if(!state.ai?.vision_ready||state.meta.platform!=='local')return;if(state.inLiveCall||now<state.lastLiveTime+8||now===0)return;
  state.lastLiveTime=now;let canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;
  try{
    canvas.getContext('2d').drawImage(video,0,0,640,360);
    const img=canvas.toDataURL('image/jpeg',.72).split(',')[1];state.inLiveCall=true;
    $('narrationStatus').textContent='AI 正在辨識影格…';
    const data=await apiPost(`/api/videos/${state.meta.id}/live`,{at:now,image:img});
    if(state.mode!=='live')return;
    const ev=data.event;state.cues.push({id:ev.id,t:ev.t,narration:ev.narration,source:ev.source});
    if(currentTime()-now>5){setNarration(ev.narration,'AI 觀察完成 · 延遲較久，未語音插播')}
    else if(ev.narration){setNarration(ev.narration,'Live AI · 未經人工驗證');speech(ev.narration)}
    await fetchMemory(true);
  }catch(e){toast(e.message,'error');setMode('prepared')}finally{state.inLiveCall=false}
}
function pushChat(text,who,source=''){let box=li($('chatMessages'),`chat-bubble ${who}`,text);if(source)li(box,'chat-note',source);$('chatMessages').scrollTop=$('chatMessages').scrollHeight;return box}
async function sendQuestion(q){q=(q||'').trim();if(!q||!state.meta||state.qaBusy)return;state.qaBusy=true;$('sendBtn').disabled=true;pushChat(q,'user');const at=currentTime();$('qaStatus').textContent='正在查詢…';
  try{let res=await apiPost(`/api/videos/${state.meta.id}/qa`,{question:q,at});const labels={demo_authored_qa:'人工示範問答',ollama_time_filtered:'本機 AI · 僅已觀看事件',keyword_retrieval:'關鍵字檢索 · 非生成式AI',no_evidence:'尚無資料',no_match:'無直接證據'};const note=`${labels[res.source]||res.source} · 播放至 ${fmt(at)}`;pushChat(res.answer,'assistant',note);$('qaStatus').textContent='已依時間篩選';if(state.voiceEnabled)speech(res.answer)}catch(e){pushChat('抱歉，問答未完成：'+e.message,'assistant');$('qaStatus').textContent='錯誤'}finally{state.qaBusy=false;$('sendBtn').disabled=false}
}
function openModal(title,body,confirm='確認'){$('modalTitle').textContent=title;$('modalBody').innerHTML=body;$('modalConfirm').textContent=confirm;$('modal').showModal();return new Promise(resolve=>{function onClose(){$('modal').removeEventListener('close',onClose);resolve($('modal').returnValue==='ok')} $('modal').addEventListener('close',onClose)})}
async function addManual(){if(!state.meta||state.meta.demo)return;let html=`<p class="muted">新增的事件會標示「人工標註」，可用來建立自有的口述資料包。</p><label>時間點（秒）<input id="manualAt" type="number" min="0" step="0.1" value="${currentTime().toFixed(1)}" required></label><label>事件描述<textarea id="manualDescription" placeholder="例：一名男子拿起桌上的鑰匙" required></textarea></label><label>語音口述<textarea id="manualNarration" placeholder="例：男子悄悄拿走桌上的鑰匙" required></textarea></label>`;
  if(!await openModal('新增人工事件',html,'儲存事件'))return;
  try{const value={at:parseFloat($('manualAt').value),description:$('manualDescription').value,narration:$('manualNarration').value};if(!value.description||!value.narration||!isFinite(value.at))throw new Error('請填寫完整資料');await apiPost(`/api/videos/${state.meta.id}/events`,value);toast('已加入人工標註事件','success');const cues=await request(`/api/videos/${state.meta.id}/cues`);state.cues=cues.cues;await fetchMemory(true);refreshCatalog()}catch(e){toast(e.message,'error')}
}
async function createYouTube(){let html='<p class="muted">官方嵌入播放器能同步影片播放時間，但不會取得 YouTube 影片畫面供 AI 解析。口述需要自行匯入授權的時間軸資料。</p><label>YouTube 影片網址<input id="youtubeUrl" type="url" placeholder="https://www.youtube.com/watch?v=..." required></label>';
  if(!await openModal('新增 YouTube 同步',html,'建立播放器'))return;
  try{const row=await apiPost('/api/videos/youtube',{url:$('youtubeUrl').value.trim()});state.catalog.unshift(row);await selectVideo(row.id);toast('YouTube 播放器建立成功。請匯入相對應的口述 JSON。','success')}catch(e){toast(e.message,'error')}
}
async function importJson(file){if(!state.meta||state.meta.demo)return toast('請先選擇自行上傳的影片或 YouTube 播放器','error');try{
  const data=JSON.parse(await file.text());if(!Array.isArray(data.events)||!data.events.length)throw new Error('JSON 需包含 events 陣列');
  const res=await apiPost(`/api/videos/${state.meta.id}/timeline/import`,{events:data.events,characters:data.characters||[]});toast(`成功匯入 ${res.count} 筆事件；資料為人工匯入，非 AI 辨識。`,'success');await selectVideo(state.meta.id);setMode('prepared');
}catch(e){toast(e.message,'error')}}
async function prepareVideo(){if(!state.meta)return;try{const {job_id}=await apiPost(`/api/videos/${state.meta.id}/prepare`,{});$('jobProgress').hidden=false;$('jobProgressBar').style.width='0%';$('prepareBtn').disabled=true;toast('已啟動本機 AI 分析。影片越長所需時間越久。');
  const timer=setInterval(async()=>{try{let d=await request(`/api/jobs/${job_id}`);$('jobMessage').textContent=d.message;$('jobProgressBar').style.width=(d.total?Math.round(d.progress/d.total*100):1)+'%';if(d.state==='done'||d.state==='error'){clearInterval(timer);$('prepareBtn').disabled=false;if(d.state==='done'){toast(d.message,'success');await selectVideo(state.meta.id);setMode('prepared')}else toast(d.message,'error')}}catch(e){clearInterval(timer);toast(e.message,'error')}},1250)
}catch(e){toast(e.message,'error')}}
async function uploadVideo(file){if(!file)return;if(file.size>200*1024*1024)return toast('上傳上限 200 MB','error');toast('正在匯入影片…');let form=new FormData();form.append('file',file);try{let meta=await request('/api/videos/upload',{method:'POST',body:form});state.catalog.unshift(meta);await selectVideo(meta.id);toast('影片已匯入，可啟用 Live AI 或預處理分析。','success')}catch(e){toast(e.message,'error')}}
async function refreshCatalog(){try{state.catalog=await request('/api/videos');paintLibrary()}catch(e){toast(e.message,'error')}}
function setupMicrophone(){let Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition)return toast('此瀏覽器不支援語音辨識，可使用鍵盤輸入。建議 Chrome 或 Edge。','error');try{let recognition=new Recognition();recognition.lang='zh-TW';recognition.interimResults=false;recognition.maxAlternatives=1;recognition.onresult=event=>{$('questionInput').value=event.results[0][0].transcript;$('questionInput').focus()};recognition.onerror=e=>toast('麥克風辨識未成功：'+e.error,'error');recognition.start();toast('正在聆聽，請開始說話…')}catch(e){toast('無法啟用麥克風：'+e.message,'error')}}
function setUiListeners(){
  $('playPause').onclick=togglePlay;$('skipBack').onclick=()=>seekTo(currentTime()-5);$('skipForward').onclick=()=>seekTo(currentTime()+5);
  $('seekBar').addEventListener('input',()=>{state.isSeeking=true;$('currentTime').textContent=fmt(Number($('seekBar').value))});$('seekBar').addEventListener('change',()=>{state.isSeeking=false;seekTo(Number($('seekBar').value))});
  $('muteOriginal').onclick=()=>{if(state.meta?.platform==='youtube'){if(state.ytReady){state.yt.isMuted()?state.yt.unMute():state.yt.mute()}}else video.muted=!video.muted;toast('已切換影片原聲靜音')};
  $('fullscreen').onclick=()=>{let stage=$('videoStage');if(document.fullscreenElement)document.exitFullscreen();else stage.requestFullscreen?.()};
  $('preparedMode').onclick=()=>setMode('prepared');$('liveMode').onclick=()=>setMode('live');$('prepareBtn').onclick=prepareVideo;$('manualBtn').onclick=addManual;
  $('voiceToggle').onchange=e=>{state.voiceEnabled=e.target.checked;if(!state.voiceEnabled)speechSynthesis.cancel();toast(state.voiceEnabled?'已開啟語音口述':'已關閉語音口述')};
  $('speechRate').oninput=e=>$('speechRateLabel').textContent=(+e.target.value).toFixed(1)+'×';
  $('showCaptions').onchange=e=>{state.subtitlesEnabled=e.target.checked;$('narrationOverlay').hidden=!state.subtitlesEnabled};
  $('chatForm').onsubmit=e=>{e.preventDefault();let q=$('questionInput').value;$('questionInput').value='';sendQuestion(q)};
  $('micBtn').onclick=setupMicrophone;$('questionSuggestions').onclick=e=>{const q=e.target.closest('[data-question]');if(q)sendQuestion(q.dataset.question)};
  $('refreshStatus').onclick=refreshAI;$('youtubeBtn').onclick=createYouTube;
  $('uploadInput').onchange=e=>{const f=e.target.files?.[0];uploadVideo(f);e.target.value=''};
  $('importTimeline').onchange=e=>{const f=e.target.files?.[0];if(f)importJson(f);e.target.value=''};
  video.addEventListener('loadedmetadata',updateClock);video.addEventListener('ended',()=>{speechSynthesis.cancel();updateClock()});video.addEventListener('pause',updateClock);video.addEventListener('play',updateClock);
  $('helpBtn').onclick=()=>openModal('使用 StoryBridge',`<p>① 左側選擇展示影片或匯入合法取得的影片。</p><p>② 「預處理」模式使用已有事件時間軸；「Live AI」需要本機 Ollama 視覺模型。</p><p>③ 按下播放，系統會用瀏覽器中文語音合成在事件時點朗讀描述。若沒有中文系統語音，仍可閱讀字幕。</p><p>④ 在右側詢問已播放的劇情。展示問答是人工標註；其他影片可使用 Ollama 或關鍵字事件檢索。</p><p>⑤ YouTube 為合法播放器時間同步展示，無法自動抽取 YouTube 畫面。</p><p><strong>快捷鍵：</strong>空白鍵播放/暫停；Q 前往問答；N 切換口述。</p><p>AI 觀察不等同於確認角色真實身分，切勿把模型猜測當成已驗證資訊。</p>`,'知道了');
  document.addEventListener('keydown',e=>{if(e.target.matches('input,textarea,select')||$('modal').open)return;if(e.code==='Space'){e.preventDefault();togglePlay()}if(e.key.toLowerCase()==='q'){$('questionInput').focus()}if(e.key.toLowerCase()==='n'){$('voiceToggle').click()}});
}
async function main(){setUiListeners();await refreshCatalog();await selectVideo('demo');await refreshAI();setInterval(tick,260);}
main().catch(e=>toast('初始化失敗：'+e.message,'error'));
