import { useState, useEffect } from 'react'
import { host, useQuery, useQueryClient, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, THEMES_AREA } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

// ── Встречи: дашборд обработанных встреч (стиль Штурмана, просмотр + открытие файлов) ──
// Вкладка /meetings в сайдбаре. Backend: dashboard/plugin_api.py → /api/plugins/meeting-intelligence/*
// ctx.rest('/meetings') → список встреч и артефактов; открытие файла — через GET .../file/<name>.

let _ctx = null
const restGet = (path) => {
  if (!_ctx) return Promise.reject(new Error('plugin context not ready'))
  return _ctx.rest(path)
}
const restCall = (path, opts) => {
  if (!_ctx) return Promise.reject(new Error('plugin context not ready'))
  return _ctx.rest(path, opts)
}

// ── Проверка обновлений плагина (git) + кнопка «Обновить» ──────────────
const UPD_BASE = { display:'inline-flex', alignItems:'center', gap:6, borderRadius:999, border:'1px solid var(--st-line, #e6e6e2)', background:'var(--st-surface, #fff)', color:'var(--st-muted, #6a6a6a)', fontSize:12, fontWeight:700, padding:'7px 12px', cursor:'pointer', fontFamily:'inherit', lineHeight:1, whiteSpace:'nowrap' }
const UPD_ON = { borderColor:'var(--st-accent, #ff385c)', color:'#fff', background:'var(--st-accent, #ff385c)' }
function useUpdateStatus() {
  return useQuery({ queryKey: ['upd','status','meeting'], queryFn: () => restGet('/update/status'), refetchInterval: 6*3600*1000, retry: 0 })
}
function UpdatePill() {
  const qc = useQueryClient()
  const q = useUpdateStatus()
  const [busy, setBusy] = useState(false)
  const d = (q.data && typeof q.data === 'object') ? q.data : null
  const behind = (d && Number(d.behind)) || 0
  const ua = !!(d && d.updates_available)
  const apply = async () => {
    if (busy) return
    setBusy(true)
    try {
      const r = await restCall('/update/apply', { method: 'POST' })
      const ok = !!(r && r.ok)
      try { host.notify({ kind: ok ? 'success' : 'error', message: ok ? 'Готово — перезапустите Hermes (⌘Q / Ctrl+K → Reload desktop plugins).' : 'Обновление не удалось: ' + ((r && (r.stderr || r.stdout)) || 'см. лог') }) } catch (_) {}
      qc.invalidateQueries({ queryKey: ['upd','status'] })
    } catch (e) { try { host.notify({ kind:'error', message:'Ошибка: '+((e&&e.message)||e) }) } catch(_) {} }
    finally { setBusy(false) }
  }
  if (q.isLoading) return jsx('span', { style: UPD_BASE, title: 'Проверка обновлений…', children: '↻' })
  return jsx('button', {
    style: Object.assign({}, UPD_BASE, ua ? UPD_ON : null, busy ? { opacity:.6 } : null),
    title: ua ? ('Доступно обновлений: '+behind+(d&&d.log&&d.log.length?'\n'+d.log.join('\n'):'')) : 'Обновлений нет — клик чтобы перепроверить',
    onClick: () => ua ? apply() : qc.invalidateQueries({ queryKey: ['upd','status'] }),
    disabled: busy,
    children: busy ? '↻…' : (ua ? ('↻ Обновить'+(behind?(' ('+behind+')'):'')) : '↻')
  })
}

// ctx.rest() возвращает уже распарсенный объект (FastAPI auto-serializes) либо { result: "..." }.
const parseRest = (r) => {
  if (r == null) return {}
  if (typeof r === 'object' && typeof r.result === 'string') {
    try { return JSON.parse(r.result) } catch (_) { return { raw: r.result } }
  }
  return r
}

const MOUNT = '/api/plugins/meeting-intelligence'
const openFile = async (name, file, forceDownload) => {
  // Открытие артефакта: бэкенд открывает файл в приложении ОС (Word/Excel/блокнот)
  // через POST .../file/<name>/open (os.startfile / open / xdg-open). Вебвью
  // сам не умеет рендерить .docx, а Blob+a.download лишь сохраняет файл.
  // Скачивание (authed ctx.rest → JSON+base64 → Blob) — фолбэк и Shift+клик.
  if (!forceDownload) {
    try {
      const r = await restCall('/meetings/' + encodeURIComponent(name) + '/file/' + encodeURIComponent(file) + '/open', { method: 'POST' })
      if (r && r.ok) return
      throw new Error((r && r.detail) || 'бэкенд не открыл файл')
    } catch (e) {
      try { host.notify({ kind: 'error', message: 'Не удалось открыть файл (' + (((e && e.message) || e)) + ') — скачиваю копию.' }) } catch (_) {}
    }
  }
  try {
    const d = await restGet('/meetings/' + encodeURIComponent(name) + '/file/' + encodeURIComponent(file) + '/data')
    if (!d || !d.base64) throw new Error('нет данных файла')
    const bin = atob(d.base64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    const blob = new Blob([bytes], { type: d.contentType || 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = d.filename || file
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 15000)
  } catch (e) {
    try { host.notify({ kind: 'error', message: 'Не удалось скачать файл: ' + ((e && e.message) || e) }) } catch (_) {}
  }
}

// ── запуск пайплайна: открыть сессию агента с skill meeting-intelligence ──
const MEETING_PROMPT = (src, opts) => {
  const o = opts || {}
  const parts = ['Обработай материал (встреча/лекция/интервью/презентация): ' + src + '.']
  parts.push('Примени skill meeting-intelligence: сначала определи тип контента и язык, затем транскрибируй локальным Whisper (если это URL/media — скачай аудио через yt-dlp).')
  if (o.translate !== false) parts.push('Если язык не русский — переведи транскрипт на русский.')
  parts.push('Затем извлеки артефакты строго по правилам skill: протокол (для встречи), саммари, аналитическая записка, реестр решений, поручения. Каждое решение/поручение — с source_quote из транскрипта; не выдумывай имена, роли, дедлайны.')
  parts.push('Готовые файлы (.docx/.xlsx/.txt) сохрани в папку встречи в MEETING_ROOT. В конце — краткий отчёт, что создано.')
  if (o.cloud) parts.push('Разрешён cloud LLM (--allow-cloud).')
  if (o.language && o.language !== 'auto') parts.push('Язык исходника: ' + o.language + '.')
  return parts.join(' ')
}
const openMeetingSession = async (src, opts, knownMeetings) => {
  const short = (String(src || '').trim().split(/[\\/]/).pop() || 'материал').slice(0, 60)
  try {
    const created = await host.request('session.create', { source: 'desktop', title: 'Встреча: ' + short })
    const sid = created && (created.session_id || created.stored_session_id || (created.session && created.session.id) || created.id)
    if (!sid) throw new Error('session.create вернул пустой id')
    try { await host.request('prompt.submit', { session_id: sid, text: MEETING_PROMPT(src, opts) }) } catch (_) {}
    savePending({ sid: String(sid), src: String(src).slice(0, 120), name: short, startedAt: Date.now(), known: Array.isArray(knownMeetings) ? knownMeetings.slice(0, 200) : [] })
    try { host.notify({ kind: 'success', message: 'Пайплайн запущен — транскрипция и анализ пошли. Прогресс виден ниже.' }) } catch (_) {}
    return String(sid)
  } catch (e) {
    try { host.notify({ kind: 'error', message: 'Не удалось открыть сессию: ' + ((e && e.message) || e) }) } catch (_) {}
    return null
  }
}
const PJ_KEY = 'meet.pendingJob'
const loadPending = () => { try { const j = JSON.parse(localStorage.getItem(PJ_KEY) || 'null'); return (j && j.sid && j.startedAt) ? j : null } catch (_) { return null } }
const savePending = (j) => { try { localStorage.setItem(PJ_KEY, JSON.stringify(j)) } catch (_) {} }
const clearPending = () => { try { localStorage.removeItem(PJ_KEY) } catch (_) {} }
const fmtElapsed = (ms) => { const s = Math.max(0, Math.floor((ms || 0) / 1000)); const m = Math.floor(s / 60); return m > 0 ? (m + 'м ' + (s % 60) + 'с') : (s + 'с') }

// ── helpers ──
const fmtRu = (d) => {
  const s = (d || '').slice(0, 10)
  if (!s) return '—'
  const [y, m, dd] = s.split('-')
  return `${dd}.${m}.${y}`
}
const fmtName = (n) => { const s = (n || '').replace(/^\d{4}-\d{2}-\d{2}_?/, ''); return s || n }
const fmtSize = (b) => {
  if (b == null) return ''
  if (b < 1024) return b + ' Б'
  if (b < 1048576) return (b / 1024).toFixed(0) + ' КБ'
  return (b / 1048576).toFixed(1) + ' МБ'
}
const fmtBytes = (n) => {
  const b = Number(n) || 0
  if (b < 1024) return b + ' Б'
  if (b < 1048576) return (b / 1024).toFixed(0) + ' КБ'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + ' МБ'
  return (b / 1073741824).toFixed(1) + ' ГБ'
}
const basename = (p) => { try { const s = String(p).replace(/[\\/]+$/, ''); return s.slice(s.replace(/\\/g, '/').lastIndexOf('/') + 1) } catch (_) { return p } }
const plural = (n, one, few, many) => { const m10 = n % 10, m100 = n % 100; if (m10 === 1 && m100 !== 11) return one; if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few; return many }

const KIND_LABEL = {
  'Протокол.docx': 'Протокол', 'Саммари.docx': 'Саммари', 'Аналитическая_записка.docx': 'Аналитика',
  'Реестр_решений.xlsx': 'Реестр решений', 'Список_поручений.xlsx': 'Поручения',
  'Подробный конспект.docx': 'Конспект', 'План действий.docx': 'План действий',
}
const artLabel = (a) => KIND_LABEL[a.file] || (a.file || '').replace(/\.[^.]+$/, '')

// тип встречи из имени папки {date}_{type}_{topic}
const TYPE_RULES = [
  { re: /лекци/i, label: 'Лекция', cls: 'warn' },
  { re: /интервью/i, label: 'Интервью', cls: 'good' },
  { re: /презентаци|питч|демо/i, label: 'Презентация', cls: 'accent' },
  { re: /совещан|стендап|standup|синк/i, label: 'Совещание', cls: 'accent' },
  { re: /call|звонок|созвон/i, label: 'Созвон', cls: 'good' },
  { re: /встреч/i, label: 'Встреча', cls: 'accent' },
]
const detectType = (name) => { for (const t of TYPE_RULES) if (t.re.test(name)) return t; return { label: 'Встреча', cls: 'accent' } }

// ───────────────────────────────── design system ─────────────────────────────────
const CSS = `
.meet{--st-canvas:#f7f7f5;--st-surface:#fff;--st-ink:#222;--st-muted:#6a6a6a;--st-subtle:#8a8a86;
  --st-line:#e6e6e2;--st-soft:#f2f2ef;
  --st-accent:#4f46e5;--st-accent-dark:#4338ca;--st-accent-soft:#eef2ff;
  --st-good:#17835b;--st-good-soft:#eaf7f1;--st-warn:#9a6500;--st-warn-soft:#fff7df;
  --st-danger:#c13515;--st-danger-soft:#fff0ec;
  --st-r:20px;--st-rc:12px;
  --st-sh:0 0 0 1px rgba(0,0,0,.025),0 2px 6px rgba(0,0,0,.035),0 7px 22px rgba(0,0,0,.055);
  --st-font:"Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif;
  --st-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-family:var(--st-font);background:var(--st-canvas);color:var(--st-ink);min-height:100vh;box-sizing:border-box}
.meet *{box-sizing:border-box}
.meet-main{max-width:1800px;margin:0 auto;padding:28px clamp(20px,4vw,56px) 96px}
.meet-cols{column-gap:14px}
.meet-cols>.st-card{break-inside:avoid;-webkit-column-break-inside:avoid;page-break-inside:avoid}
@media(min-width:900px){.meet-cols{column-count:2}}
@media(min-width:1500px){.meet-cols{column-count:3}}

.meet-topbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}
.meet-eyebrow{color:var(--st-muted);font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  max-width:60vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meet-h1{margin:5px 0 0;font-size:clamp(27px,3vw,38px);line-height:1.1;letter-spacing:-1.2px}
.meet-pills{display:flex;gap:8px;flex-wrap:wrap}
.meet-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--st-line);background:var(--st-surface);
  border-radius:999px;padding:8px 12px;font-size:12px;font-weight:600}
.meet-disk{display:flex;align-items:center;gap:10px;margin:-8px 0 16px;padding:9px 12px;border:1px solid var(--st-line);border-radius:10px;background:var(--st-surface);color:var(--st-muted);font-size:12px;font-weight:600}
.meet-disk.danger{border-color:#f1c2b5;background:var(--st-danger-soft);color:var(--st-danger)}
.meet-storage{margin-bottom:18px}
.meet-storage-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.meet-storage-row .meet-input{min-height:38px}

.meet-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:18px}
.meet-search{min-height:36px;min-width:200px;flex:1 1 260px;border:1px solid var(--st-line);border-radius:10px;
  padding:0 12px;font-family:inherit;font-size:13px;background:#fff;color:var(--st-ink)}

.st-card{background:var(--st-surface);border-radius:var(--st-r);box-shadow:var(--st-sh);padding:20px;margin-bottom:14px;position:relative}
.m-card.open{outline:2px solid var(--st-accent-soft)}
.m-head{display:flex;justify-content:space-between;gap:12px;align-items:center;cursor:pointer}
.m-head .body{min-width:0;flex:1}
.m-head strong{display:block;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.m-head small{display:block;color:var(--st-muted);font-size:12px;margin-top:3px}
.m-body{margin-top:14px;padding-top:14px;border-top:1px solid var(--st-line)}
.m-grp{margin-bottom:12px}
.m-grp:last-child{margin-bottom:0}
.m-grp-l{font-size:10px;color:var(--st-muted);font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.m-chips{display:flex;gap:8px;flex-wrap:wrap}
.m-chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--st-line);background:var(--st-surface);
  border-radius:10px;padding:7px 11px;cursor:pointer;font-family:inherit;font-size:12px;font-weight:600;color:var(--st-ink)}
.m-chip:hover{border-color:var(--st-accent);background:var(--st-accent-soft)}
.m-chip.doc{border-color:var(--st-accent-soft);background:var(--st-accent-soft);color:var(--st-accent-dark)}
.m-chip.doc:hover{background:#e0e7ff}
.m-chip.txt{color:var(--st-muted);background:var(--st-soft)}
.m-ext{font-family:var(--st-mono);font-size:9px;font-weight:800;padding:2px 5px;border-radius:5px;background:#fff;color:var(--st-accent);border:1px solid var(--st-line)}
.m-size{font-family:var(--st-mono);font-size:10px;color:var(--st-subtle);font-weight:600}
.m-path{margin-top:12px;font-family:var(--st-mono);font-size:10px;color:var(--st-subtle);word-break:break-all}
.m-speaker{padding:10px;border:1px solid var(--st-line);border-radius:10px;background:var(--st-soft);margin-bottom:8px}
.m-speaker:last-child{margin-bottom:0}
.m-speaker-main{display:flex;gap:10px;align-items:flex-start}
.m-speaker-audio{width:190px;max-width:100%;min-height:28px;flex:0 1 190px}
.m-speaker-copy{min-width:0;flex:1;font-size:12px;line-height:1.45}
.m-speaker-meta{margin-top:4px;color:var(--st-muted);font-size:11px}
.m-speaker-form{display:grid;grid-template-columns:repeat(4,minmax(90px,1fr)) auto;gap:6px;margin-top:9px}
.m-speaker-input{min-width:0;min-height:30px;border:1px solid var(--st-line);border-radius:7px;padding:0 8px;background:#fff;color:var(--st-ink);font:inherit;font-size:11px}
@media(max-width:700px){.m-speaker-main{flex-direction:column}.m-speaker-form{grid-template-columns:repeat(2,minmax(0,1fr))}.m-speaker-form .st-copy-btn{grid-column:span 2}}

.st-badge{display:inline-flex;padding:5px 9px;border-radius:999px;font-size:9px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
.st-badge.good{color:var(--st-good);background:var(--st-good-soft)}
.st-badge.warn{color:var(--st-warn);background:var(--st-warn-soft)}
.st-badge.danger{color:var(--st-danger);background:var(--st-danger-soft)}
.st-badge.muted{color:var(--st-subtle);background:var(--st-soft)}
.st-badge.accent{color:var(--st-accent-dark);background:var(--st-accent-soft)}

.st-dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.st-dot.good{background:var(--st-good);box-shadow:0 0 0 4px var(--st-good-soft)}
.st-dot.warn{background:var(--st-warn);box-shadow:0 0 0 4px var(--st-warn-soft)}

.st-copy-btn{min-height:28px;padding:0 10px;font-size:12px;border:1px solid var(--st-line);background:var(--st-surface);
  color:var(--st-muted);border-radius:8px;cursor:pointer;font-family:inherit;font-weight:700}
.st-copy-btn:hover{color:var(--st-accent);border-color:var(--st-accent)}

.st-seg{display:flex;gap:5px;padding:4px;background:#eaeae7;border-radius:12px;flex-wrap:wrap}
.st-seg button{min-height:32px;border:0;border-radius:9px;background:transparent;padding:0 12px;cursor:pointer;
  color:var(--st-muted);font-size:12px;font-weight:700;font-family:inherit}
.st-seg button.active{background:#fff;color:var(--st-ink);box-shadow:0 1px 4px rgba(0,0,0,.08)}

.st-skel{background:#ededeb;border-radius:8px;height:46px;margin:8px 0;animation:st-pulse 1.2s ease-in-out infinite alternate}
@keyframes st-pulse{from{opacity:.45}to{opacity:1}}
.st-err{color:var(--st-muted);font-size:13px;padding:8px 0}
.st-empty{border:1px dashed #cfcfca;border-radius:14px;background:var(--st-soft);padding:28px;text-align:center;
  color:var(--st-muted);font-size:13px}

.meet-help{margin-top:6px}
.meet-help summary{cursor:pointer;font-weight:700;font-size:13px;color:var(--st-muted);list-style:none}
.meet-help summary::-webkit-details-marker{display:none}
.meet-help-body{margin-top:12px;font-size:12px;color:var(--st-muted);line-height:1.6}
.meet-help code{font-family:var(--st-mono);background:var(--st-soft);padding:2px 6px;border-radius:6px;font-size:11px;color:var(--st-ink)}
.meet-help-body p{margin:6px 0}
.st-foot{margin-top:28px;padding-top:16px;border-top:1px solid var(--st-line);color:var(--st-subtle);font-size:11px;font-family:var(--st-mono)}
.meet-process{margin-bottom:18px;padding:16px 18px;border:1px solid var(--st-line);border-radius:14px;background:linear-gradient(135deg,#f7f6ff,#fff)}
.meet-process-row{display:flex;gap:10px;flex-wrap:wrap}
.meet-input{flex:1 1 320px;min-height:40px;border:1px solid var(--st-line);border-radius:10px;padding:0 14px;font-family:inherit;font-size:13px;background:#fff;color:var(--st-ink)}
.meet-input:focus{outline:none;border-color:var(--st-accent)}
.meet-btn{min-height:40px;border-radius:10px;border:0;padding:0 16px;cursor:pointer;font-weight:700;font-size:13px;font-family:inherit}
.meet-btn.primary{background:var(--st-accent);color:#fff}
.meet-btn.primary:disabled{opacity:.5;cursor:default}
.meet-process-opts{margin-top:8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.meet-link{background:transparent;border:0;color:var(--st-muted);font-size:12px;cursor:pointer;font-family:inherit;padding:0}
.meet-link:hover{color:var(--st-accent)}
.meet-process-adv{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--st-muted)}
.meet-process-adv label{display:flex;align-items:center;gap:6px}
.meet-process-adv select{min-height:30px;border:1px solid var(--st-line);border-radius:7px;padding:0 8px;font-family:inherit;font-size:12px;background:#fff}
.meet-chk{cursor:pointer}
.meet-process-hint{margin:10px 0 0;color:var(--st-subtle);font-size:11px;line-height:1.5}
.meet-prog{margin-bottom:14px;padding:13px 16px;border:1px solid var(--st-accent,#6c5ce7);border-radius:12px;background:linear-gradient(135deg,#f6f4ff,#fff)}
.meet-prog-done{border-color:var(--st-good,#17835b);background:linear-gradient(135deg,#eaf7f1,#fff)}
.meet-prog-head{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:13px}
.meet-prog-spin{flex:0 0 auto;width:14px;height:14px;border:2px solid #e8e4ff;border-top-color:var(--st-accent,#6c5ce7);border-radius:50%;animation:meet-spin .8s linear infinite}
.meet-prog-bar{height:6px;border-radius:99px;background:var(--st-soft,#f2f2ef);overflow:hidden;position:relative}
.meet-prog-bar i{position:absolute;top:0;height:100%;width:40%;border-radius:inherit;background:var(--st-accent,#6c5ce7);animation:meet-slide 1.1s ease-in-out infinite}
.meet-prog-meta{display:flex;align-items:center;gap:10px;margin-top:8px;font-size:11px;color:var(--st-muted,#6a6a6a);flex-wrap:wrap}
@keyframes meet-spin{to{transform:rotate(360deg)}}
@keyframes meet-slide{0%{left:-40%}100%{left:100%}}
`

const THEME_COLORS = {
  background: '#f7f7f5', foreground: '#222222', card: '#ffffff', cardForeground: '#222222',
  muted: '#f0f0ee', mutedForeground: '#6a6a6a', popover: '#ffffff', popoverForeground: '#222222',
  primary: '#4f46e5', primaryForeground: '#ffffff',
  secondary: '#e0e7ff', secondaryForeground: '#4338ca',
  accent: '#eef2ff', accentForeground: '#4338ca',
  border: '#e6e6e2', input: '#e6e6e2', ring: '#4f46e5',
  midground: '#4f46e5', midgroundForeground: '#ffffff', composerRing: '#4f46e5',
  destructive: '#c13515', destructiveForeground: '#ffffff',
  sidebarBackground: '#f7f7f5', sidebarBorder: '#e6e6e2',
  userBubble: '#eef2ff', userBubbleBorder: '#e6e6e2',
}

// ───────────────────────────────── card ─────────────────────────────────
function SpeakerAudio({ name, label }) {
  const [src, setSrc] = useState('')
  const [state, setState] = useState('loading')
  useEffect(() => {
    let alive = true
    let url = ''
    const load = async () => {
      try {
        const d = await restGet('/meetings/' + encodeURIComponent(name) + '/speaker/' + encodeURIComponent(label) + '/audio?max_sec=30')
        if (!d || !d.base64) throw new Error('нет аудио')
        const bin = atob(d.base64)
        const bytes = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
        url = URL.createObjectURL(new Blob([bytes], { type: d.contentType || 'audio/wav' }))
        if (alive) { setSrc(url); setState('ready') }
      } catch (_) {
        if (alive) setState('error')
      }
    }
    load()
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [name, label])
  if (state === 'loading') return jsx('span', { className: 'm-speaker-meta', children: '▶ загрузка аудио…' })
  if (state === 'error') return jsx('span', { className: 'm-speaker-meta', children: 'нет аудио' })
  return jsx('audio', { className: 'm-speaker-audio', controls: true, src })
}

function SpeakerRow({ name, speaker }) {
  const qc = useQueryClient()
  const [fullName, setFullName] = useState(speaker.full_name || '')
  const [role, setRole] = useState(speaker.role || '')
  const [contact, setContact] = useState(speaker.contact || '')
  const [short, setShort] = useState(speaker.short || speaker.label || '')
  const [saving, setSaving] = useState(false)
  const save = async () => {
    if (saving) return
    setSaving(true)
    try {
      const r = await restCall('/meetings/' + encodeURIComponent(name) + '/speaker/' + encodeURIComponent(speaker.label) + '/label', { method: 'POST', body: { full_name: fullName, role, contact, short } })
      if (!r || !r.ok) throw new Error('не удалось сохранить')
      try { host.notify({ kind: 'success', message: 'Метка спикера сохранена' }) } catch (_) {}
      qc.invalidateQueries({ queryKey: ['meet', 'speakers', name] })
    } catch (e) {
      try { host.notify({ kind: 'error', message: 'Ошибка: ' + ((e && e.message) || e) }) } catch (_) {}
    } finally { setSaving(false) }
  }
  return jsxs('div', { className: 'm-speaker', children: [
    jsxs('div', { className: 'm-speaker-main', children: [
      jsx(SpeakerAudio, { name, label: speaker.label }),
      jsxs('div', { className: 'm-speaker-copy', children: [
        jsx('div', { className: 'st-selectable', children: speaker.sample_line || '—' }),
        jsx('div', { className: 'm-speaker-meta', children: (speaker.count || 0) + ' реплик · ' + Math.round(Number(speaker.total_dur_sec) || 0) + 'с' }),
      ] }),
    ] }),
    jsxs('div', { className: 'm-speaker-form', children: [
      jsx('input', { className: 'm-speaker-input', placeholder: 'ФИО', value: fullName, onInput: (e) => setFullName(e.target.value) }),
      jsx('input', { className: 'm-speaker-input', placeholder: 'Должность', value: role, onInput: (e) => setRole(e.target.value) }),
      jsx('input', { className: 'm-speaker-input', placeholder: 'Контакт', value: contact, onInput: (e) => setContact(e.target.value) }),
      jsx('input', { className: 'm-speaker-input', placeholder: 'Short', value: short, onInput: (e) => setShort(e.target.value) }),
      jsx('button', { className: 'st-copy-btn', disabled: saving, onClick: save, children: saving ? 'Сохраняю…' : 'Сохранить' }),
    ] }),
  ] })
}

function MeetingSpeakers({ name }) {
  const sq = useQuery({ queryKey: ['meet', 'speakers', name], queryFn: () => restGet('/meetings/' + encodeURIComponent(name) + '/speakers'), enabled: false })
  useEffect(() => { sq.refetch() }, [name])
  const speakers = sq.data && sq.data.speakers
  if (!speakers || !speakers.length) return null
  return jsxs('div', { className: 'm-grp', children: [
    jsx('div', { className: 'm-grp-l', children: '🎤 Спикеры' }),
    jsx('div', { children: speakers.map((speaker) => jsx(SpeakerRow, { name, speaker }, speaker.label)) }),
  ] })
}

function MeetingCard({ m, expanded, onToggle }) {
  const t = detectType(m.name)
  const docs = (m.artifacts || []).filter((a) => a.kind === 'docx')
  const txts = (m.artifacts || []).filter((a) => a.kind === 'txt')
  return jsxs('article', { className: 'st-card m-card' + (expanded ? ' open' : ''), children: [
    jsxs('div', { className: 'm-head', onClick: onToggle, children: [
      jsxs('div', { className: 'body', children: [
        jsxs('div', { children: [jsx('strong', { children: fmtName(m.name) }), jsx('span', { className: 'st-badge ' + t.cls, style: { marginLeft: 8 }, children: t.label })] }),
        jsxs('small', { children: [fmtRu(m.date), ' · ', m.file_count, ' ', plural(m.file_count, 'файл', 'файла', 'файлов')] }),
      ] }),
      jsxs('div', { className: 'meet-pills', children: [
        docs.length ? jsx('span', { className: 'st-badge accent', children: docs.length + ' док' }) : null,
        jsx('button', { className: 'st-copy-btn', children: expanded ? '▴ свернуть' : '▾ открыть' }),
      ] }),
    ] }),
    expanded ? jsxs('div', { className: 'm-body', children: [
      docs.length ? jsxs('div', { className: 'm-grp', children: [
        jsx('div', { className: 'm-grp-l', children: 'Документы — нажмите, чтобы открыть' }),
        jsx('div', { className: 'm-chips', children: docs.map((a) => jsxs('button', { className: 'm-chip doc', title: (a.path || '') + ' · Shift+клик — скачать', onClick: (e) => openFile(m.name, a.file, e.shiftKey), children: [
          jsx('span', { children: artLabel(a) }),
          jsx('span', { className: 'm-ext', children: (a.ext || 'doc').toUpperCase() }),
          a.size ? jsx('span', { className: 'm-size', children: fmtSize(a.size) }) : null,
        ] }, a.file)) }),
      ] }) : null,
      txts.length ? jsxs('div', { className: 'm-grp', children: [
        jsx('div', { className: 'm-grp-l', children: 'Транскрипты' }),
        jsx('div', { className: 'm-chips', children: txts.map((a) => jsxs('button', { className: 'm-chip txt', title: (a.path || '') + ' · Shift+клик — скачать', onClick: (e) => openFile(m.name, a.file, e.shiftKey), children: [
          jsx('span', { children: artLabel(a) }),
          a.size ? jsx('span', { className: 'm-size', children: fmtSize(a.size) }) : null,
        ] }, a.file)) }),
      ] }) : null,
      jsx(MeetingSpeakers, { name: m.name }),
      jsxs('div', { className: 'm-path', children: ['📁 ', m.path] }),
    ] }) : null,
  ] })
}

// ───────────────────────────────── main ─────────────────────────────────
// ── Форма запуска пайплайна (путь/ссылка → сессия агента с skill) ──
function ProcessForm({ onDone, knownMeetings }) {
  const [src, setSrc] = useState('')
  const [lang, setLang] = useState('auto')
  const [translate, setTranslate] = useState(true)
  const [cloud, setCloud] = useState(false)
  const [busy, setBusy] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const submit = async () => {
    const s = src.trim()
    if (!s || busy) return
    setBusy(true)
    const sid = await openMeetingSession(s, { language: lang, translate, cloud }, knownMeetings)
    setBusy(false)
    if (sid) { setSrc(''); onDone && onDone(sid) }
  }
  return jsxs('div', { className: 'meet-process', children: [
    jsxs('div', { className: 'meet-process-row', children: [
      jsx('input', { className: 'meet-input', placeholder: 'Путь к файлу или ссылка (https://…)', value: src, onInput: (e) => setSrc(e.target.value), onKeyDown: (e) => { if (e.key === 'Enter') submit() } }),
      jsx('button', { className: 'meet-btn primary', disabled: busy || !src.trim(), onClick: submit, children: busy ? 'Запускаю…' : '▶ Запустить пайплайн' }),
    ] }),
    jsxs('div', { className: 'meet-process-opts', children: [
      jsx('button', { className: 'meet-link', onClick: () => setAdvanced(a => !a), children: (advanced ? '▾' : '▸') + ' Параметры' }),
      advanced ? jsxs('div', { className: 'meet-process-adv', children: [
        jsxs('label', { children: ['Язык ', jsx('select', { value: lang, onChange: (e) => setLang(e.target.value), children: [['auto', 'Авто'], ['ru', 'Русский'], ['en', 'English']].map(([v, l]) => jsx('option', { value: v, children: l }, v)) })] }),
        jsxs('label', { className: 'meet-chk', children: [jsx('input', { type: 'checkbox', checked: translate, onChange: (e) => setTranslate(e.target.checked) }), ' перевод в RU'] }),
        jsxs('label', { className: 'meet-chk', children: [jsx('input', { type: 'checkbox', checked: cloud, onChange: (e) => setCloud(e.target.checked) }), ' cloud LLM (--allow-cloud)'] }),
      ] }) : null,
    ] }),
    jsx('p', { className: 'meet-process-hint', children: 'Агент транскрибирует (Whisper; URL→yt-dlp), извлечёт протокол/саммари/аналитику и сохранит артефакты в папку встречи. Список ниже обновится сам (рефреш 60 с).' }),
  ] })
}

// ── Панель прогресса пайплайна (показывает, что обработка идёт) ──
const PROG_STAGES = ['Определяем тип контента и язык…', 'Транскрибируем аудио (Whisper)…', 'Переводим транскрипт…', 'Извлекаем протокол и артефакты…', 'Финализируем документы…']
function ProgressPanel({ meetings }) {
  const [job, setJob] = useState(loadPending)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => { setNow(Date.now()); setJob(loadPending()) }, 1000)
    return () => clearInterval(t)
  }, [])
  const known = (job && job.known) || []
  const appeared = job ? (meetings || []).filter((m) => m && m.name && !known.includes(m.name)).map((m) => m.name) : []
  const done = appeared.length > 0
  useEffect(() => {
    if (!done) return
    const t = setTimeout(() => { clearPending(); setJob(null) }, 8000)
    return () => clearTimeout(t)
  }, [done])
  if (!job) return null
  const elapsed = fmtElapsed(now - (job.startedAt || now))
  const stageIdx = Math.min(PROG_STAGES.length - 1, Math.floor((now - (job.startedAt || now)) / 30000))
  const open = () => { try { host.request('session.activate', { session_id: job.sid }) } catch (_) {} try { host.navigate('/session/' + encodeURIComponent(job.sid)) } catch (_) {} }
  if (done) return jsxs('div', { className: 'meet-prog meet-prog-done', children: [
    jsx('div', { className: 'meet-prog-head', children: jsx('strong', { children: '✓ Готово — встреча появилась в списке' }) }),
    appeared.length ? jsx('div', { style: { fontSize: 12, color: 'var(--st-muted)' }, children: appeared.join(', ') }) : null,
    jsxs('div', { className: 'meet-prog-meta', children: ['⏱ ' + elapsed, jsx('button', { className: 'st-copy-btn', style: { marginLeft: 'auto' }, onClick: () => { clearPending(); setJob(null) }, children: 'скрыть' })] }),
  ] })
  return jsxs('div', { className: 'meet-prog', children: [
    jsxs('div', { className: 'meet-prog-head', children: [
      jsx('span', { className: 'meet-prog-spin' }),
      jsx('strong', { children: 'Обработка:' }),
      jsx('span', { className: 'st-selectable', style: { color: 'var(--st-muted)', fontSize: 12 }, children: job.name }),
    ] }),
    jsx('div', { className: 'meet-prog-bar', children: jsx('i', {}) }),
    jsxs('div', { className: 'meet-prog-meta', children: [
      jsx('span', { children: '⏱ ' + elapsed }),
      jsx('span', { style: { color: 'var(--st-subtle)' }, children: PROG_STAGES[stageIdx] }),
      jsx('button', { className: 'st-copy-btn', style: { marginLeft: 'auto' }, onClick: open, title: 'Открыть сессию агента (реальный прогресс в чате)', children: 'открыть сессию' }),
      jsx('button', { className: 'st-copy-btn', onClick: () => { clearPending(); setJob(null) }, title: 'Скрыть панель (обработка продолжится в сессии)', children: '✕' }),
    ] }),
  ] })
}

function StorageGate({ config, qc }) {
  const [root, setRoot] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (config && config.root) setRoot((value) => value || config.root) }, [config && config.root])
  const create = async () => {
    if (busy) return
    setBusy(true)
    try {
      const r = await restCall('/storage/config', { method: 'POST', body: { root } })
      if (!r || !r.ok) throw new Error('не удалось создать структуру')
      qc.invalidateQueries({ queryKey: ['meet', 'storage'] })
      qc.invalidateQueries({ queryKey: ['meet', 'list'] })
      try { host.notify({ kind: 'success', message: 'Структура хранения встреч создана' }) } catch (_) {}
    } catch (e) {
      try { host.notify({ kind: 'error', message: 'Ошибка: ' + ((e && e.message) || e) }) } catch (_) {}
    } finally { setBusy(false) }
  }
  return jsxs('section', { className: 'st-card meet-storage', children: [
    jsx('strong', { children: '📁 Где хранить встречи?' }),
    jsx('div', { className: 'meet-storage-row', children: [
      jsx('input', { className: 'meet-input', placeholder: (config && config.root) || 'Путь к папке встреч', value: root, onInput: (e) => setRoot(e.target.value) }),
      jsx('button', { className: 'meet-btn primary', disabled: busy, onClick: create, children: busy ? 'Создаю…' : 'Создать структуру' }),
    ] }),
  ] })
}

function DiskStatus({ data }) {
  if (!data) return null
  return jsxs('div', { className: 'meet-disk' + (data.low_space ? ' danger' : ''), children: [
    jsx('span', { children: '💾 ' + (data.meetings || 0) + ' встреч · ' + fmtBytes(data.used_bytes) + ' · на диске свободно ' + (data.free_bytes ? fmtBytes(data.free_bytes) : '—') + (data.free_pct != null ? ' (' + data.free_pct + '%)' : '') }),
    data.low_space ? jsx('span', { children: '⚠ Мало места на диске — очистите старое' }) : null,
  ] })
}

function MeetingsApp() {
  // Пока идёт обработка (pendingJob) — рефреш 10 с, чтобы «Готово» появилось быстро; иначе 60 с.
  const { data: raw, isLoading, error } = useQuery({ queryKey: ['meet', 'list'], queryFn: async () => parseRest(await restGet('/meetings')), refetchInterval: () => (loadPending() ? 10000 : 60000) })
  const cfgQ = useQuery({ queryKey: ['meet', 'storage'], queryFn: () => restGet('/storage/config'), refetchInterval: 0 })
  const diskQ = useQuery({ queryKey: ['meet', 'disk'], queryFn: () => restGet('/storage/status'), refetchInterval: 300000 })
  const [q, setQ] = useState('')
  const [typeF, setTypeF] = useState('all')
  const [openId, setOpenId] = useState(null)
  const qc = useQueryClient()

  const meetings = (raw && raw.meetings) || []
  const rootErr = raw && raw.error
  const rootPath = raw && raw.root

  // доступные типы (для фильтра)
  const types = []
  meetings.forEach((m) => { const lb = detectType(m.name).label; if (!types.includes(lb)) types.push(lb) })

  const filtered = meetings.filter((m) => {
    if (typeF !== 'all' && detectType(m.name).label !== typeF) return false
    if (q.trim()) { const hay = (m.name + ' ' + (m.artifacts || []).map((a) => a.file).join(' ')).toLowerCase(); if (!hay.includes(q.trim().toLowerCase())) return false }
    return true
  })

  return jsxs('div', { className: 'meet', children: [
    jsx('style', { children: CSS }),
    jsxs('div', { className: 'meet-main', children: [
      jsxs('header', { className: 'meet-topbar', children: [
        jsxs('div', { children: [
          jsx('div', { className: 'meet-eyebrow', title: rootPath || '', children: rootPath ? ('📁 ' + basename(rootPath)) : 'папка встреч' }),
          jsx('h1', { className: 'meet-h1', children: 'Встречи' }),
        ] }),
        jsxs('div', { className: 'meet-pills', children: [
          jsxs('span', { className: 'meet-pill', children: [jsx('i', { className: 'st-dot good' }), meetings.length + ' ' + plural(meetings.length, 'встреча', 'встречи', 'встреч')] }),
          jsx(UpdatePill, {}),
        ] }),
      ] }),

      jsx(DiskStatus, { data: diskQ.data }),
      cfgQ.data && !cfgQ.data.configured && !(meetings && meetings.length) ? jsx(StorageGate, { config: cfgQ.data, qc }) : null,

      meetings.length > 0 ? jsxs('div', { className: 'meet-tools', children: [
        jsx('div', { className: 'st-seg', children: [['all', 'Все']].concat(types.map((t) => [t, t])).map(([id, label]) => jsx('button', { className: typeF === id ? 'active' : '', onClick: () => setTypeF(id), children: label }, id)) }),
        jsx('input', { className: 'meet-search', placeholder: 'Поиск по имени или файлу…', value: q, onInput: (e) => setQ(e.target.value) }),
      ] }) : null,

      isLoading ? jsxs('div', { children: [jsx('div', { className: 'st-skel' }), jsx('div', { className: 'st-skel' })] })
        : error ? jsx('div', { className: 'st-err', children: 'Ошибка: ' + ((error && error.message) || 'нет данных') })
        : rootErr ? jsxs('div', { className: 'st-empty', children: ['Папка встреч не найдена: ', jsx('br'), jsx('code', { style: { fontFamily: 'var(--st-mono)', fontSize: 11 }, children: rootPath })] })
        : filtered.length === 0 ? jsx('div', { className: 'st-empty', children: meetings.length ? 'Ничего не найдено по фильтру' : 'Пока нет обработанных встреч' })
        : jsx('div', { className: 'meet-cols', children: filtered.map((m) => jsx(MeetingCard, { m, expanded: openId === m.name, onToggle: () => setOpenId(openId === m.name ? null : m.name) }, m.name)) }),

      jsx(ProgressPanel, { meetings }),
      jsx(ProcessForm, { onDone: () => qc.invalidateQueries({ queryKey: ['meet', 'list'] }), knownMeetings: meetings.map((m) => m.name) }),

      jsxs('div', { className: 'st-foot', children: ['Встречи · meeting-intelligence · сканер папки, обновление каждые 60 с'] }),
    ] }),
  ] })
}

// ── Регистрация ──
export default {
  id: 'meeting-intelligence', name: 'Встречи — дашборд встреч',
  register(ctx) {
    _ctx = ctx
    try {
      ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/meetings' }, render: () => jsx(MeetingsApp, {}) })
      ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, order: 70, data: { codicon: 'microphone', label: 'Встречи', path: '/meetings' } })
      ctx.register({ id: 'open', area: PALETTE_AREA, data: { id: 'meetings.open', label: 'Встречи: дашборд встреч', keywords: ['встречи', 'meeting', 'протокол', 'транскрипт', 'лекция'], run: () => { try { host.navigate('/meetings') } catch (_) {} } } })
      ctx.register({ id: 'process', area: PALETTE_AREA, data: { id: 'meetings.process', label: 'Встречи: обработать файл/ссылку (пайплайн)', keywords: ['встреча', 'meeting', 'транскрипция', 'whisper', 'протокол', 'обработать', 'пайплайн'], run: () => { try { host.navigate('/meetings') } catch (_) {} } } })
      ctx.register({ id: 'theme', area: THEMES_AREA, data: { name: 'meetings', label: 'Встречи', description: 'Светлый дашборд встреч — белые карточки, индиго-акцент', colors: THEME_COLORS } })
    } catch (_) {}
  },
}
