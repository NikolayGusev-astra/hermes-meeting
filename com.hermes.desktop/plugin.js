import { useState } from 'react'
import { host, useQuery, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

// ── Meeting Intelligence: личный дашборд встреч ──
// Вкладка «Встречи» в сайдбаре. Backend: dashboard/plugin_api.py → /api/plugins/meeting-intelligence/*
// ctx.rest('/meetings') → GET /api/plugins/meeting-intelligence/meetings (session auth автоматически).
let _ctx = null

const restGet = (path) => {
  if (!_ctx) return Promise.reject(new Error('plugin context not ready'))
  return _ctx.rest(path)
}

// ── helpers ──
const fmtName = (n) => (n || '').replace(/^(\d{4}-\d{2}-\d{2})_/, '')
const fmtDate = (n) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(n || '')
  return m ? `${m[3]}.${m[2]}.${m[1]}` : ''
}

const KIND_LABEL = {
  'Протокол.docx': 'Протокол',
  'Саммари.docx': 'Саммари',
  'Аналитическая_записка.docx': 'Аналитика',
  'Реестр_решений.xlsx': 'Реестр решений',
  'Список_поручений.xlsx': 'Поручения',
}

// Карточка одной встречи
function MeetingCard({ m }) {
  const docs = (m.artifacts || []).filter((a) => a.kind === 'docx' || a.kind === 'xlsx')
  const trans = (m.artifacts || []).filter((a) => a.kind === 'txt')
  return jsxs('div', {
    className: 'bg-white rounded-xl border border-gray-200 p-4',
    children: [
      jsxs('div', { className: 'flex items-start justify-between gap-2', children: [
        jsxs('div', { children: [
          jsx('div', { className: 'font-semibold', children: fmtName(m.name) || m.name }),
          jsx('div', { className: 'text-xs text-gray-400', children: [fmtDate(m.name) || '—', ' · ', String(m.file_count || 0), ' файлов'] }),
        ]}),
        jsx('span', { className: 'text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-600 uppercase', children: 'встреча' }),
      ]}),
      docs.length ? jsxs('div', { className: 'mt-2 flex flex-wrap gap-1.5', children: docs.map((a, i) => {
        const label = KIND_LABEL[a.file] || a.file
        return jsx('span', { key: i, className: 'text-[11px] px-2 py-0.5 rounded bg-green-50 text-green-700 border border-green-100', title: a.path, children: label })
      }) }) : null,
      trans.length ? jsx('div', { className: 'mt-1.5 text-[11px] text-gray-400', children: 'Транскрипты: ' + trans.map((a) => a.file).join(', ') }) : null,
    ],
  })
}

function MeetingsApp() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['meetings', 'list'],
    queryFn: () => restGet('/meetings'),
    refetchInterval: 60000,
  })
  if (isLoading) return jsx('div', { className: 'p-4', children: jsx('p', { className: 'text-gray-400', children: 'Загрузка…' }) })
  if (isError) return jsx('div', { className: 'p-4', children: jsx('p', { className: 'text-red-500', children: 'Ошибка загрузки списка встреч' }) })
  const meetings = (data && data.meetings) || []
  return jsxs('div', {
    className: 'p-4 space-y-4 max-w-3xl',
    children: [
      jsxs('div', { className: 'flex items-center gap-2', children: [
        jsx('h2', { className: 'text-xl font-bold', children: 'Встречи' }),
        jsx('span', { className: 'text-xs text-gray-400', children: 'meeting-intelligence' }),
      ]}),
      jsxs('div', { className: 'grid grid-cols-1 gap-2', children: [
        jsx('div', { className: 'text-sm text-gray-500', children: 'Папка: ' + ((data && data.root) || '—') }),
        meetings.length === 0 && jsx('p', { className: 'text-sm text-gray-400', children: 'Нет обработанных встреч' }),
        meetings.map((m, i) => jsx(MeetingCard, { key: i, m })),
      ]}),
      jsxs('div', { className: 'bg-gray-50 rounded-xl border border-gray-200 p-3 text-xs text-gray-500', children: [
        jsx('div', { className: 'font-medium text-gray-600', children: 'Как обработать встречу' }),
        jsx('div', { className: 'mt-1 font-mono', children: 'meeting transcribe "встреча.webm" --language ru' }),
        jsx('div', { className: 'mt-1', children: 'Затем: meeting agent-transcript … и агент соберёт протокол/саммари/аналитику (DOCX).' }),
      ]}),
    ],
  })
}

export default {
  id: 'meeting-intelligence',
  name: 'Meeting Intelligence — встречи',
  register(ctx) {
    _ctx = ctx
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/meetings' }, render: () => jsx(MeetingsApp, {}) })
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, order: 70, data: { codicon: 'microphone', label: 'Встречи', path: '/meetings' } })
    ctx.register({ id: 'open', area: PALETTE_AREA, data: { id: 'meetings.open', label: 'Встречи: дашборд встреч', keywords: ['встречи', 'meeting', 'протокол', 'транскрипт'], run: () => { try { host.navigate('/meetings') } catch (_) {} } } })
  },
}
