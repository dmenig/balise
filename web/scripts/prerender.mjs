/**
 * Build-time prerender of the ~1 500 `/port/{slug}` pages (ADR-0001): no SSR runtime to operate,
 * and the harbour pages stay indexable and readable with JavaScript disabled (docs/13 journey 5).
 *
 *   node scripts/prerender.mjs            # uses http://localhost:8000
 *   API=https://api.balise.fr node scripts/prerender.mjs
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

const API = process.env.API ?? 'http://localhost:8000'
const DIST = process.env.DIST ?? 'dist'
const LIMIT = Number(process.env.PRERENDER_LIMIT ?? 2000)

const DISCLAIMER =
  "Aide à la planification. Ne pas utiliser pour la navigation. Les cartes marines officielles à jour restent obligatoires (division 240)."

async function harbours() {
  const response = await fetch(`${API}/v1/harbours?limit=200`)
  if (!response.ok) throw new Error(`GET /v1/harbours → ${response.status}`)
  const payload = await response.json()
  return payload.harbours.slice(0, LIMIT)
}

function shell(template, harbour, detail) {
  const free = detail?.free_spot_count ?? 0
  const total = detail?.spot_count ?? 0
  const services = (detail?.services ?? []).join(', ')
  const body = `
    <article id="prerendered">
      <h1>${harbour.name}</h1>
      <p>${free} place(s) signalée(s) libre(s) sur ${total} recensée(s).</p>
      ${detail?.vhf_channel ? `<p>VHF canal ${detail.vhf_channel}</p>` : ''}
      ${detail?.phone ? `<p>Téléphone : ${detail.phone}</p>` : ''}
      ${services ? `<p>Services : ${services}</p>` : ''}
      <p>${DISCLAIMER}</p>
      <p>${(detail?.attribution ?? []).join(' — ')}</p>
    </article>`
  return template
    .replace('<title>', `<title>${harbour.name} — `)
    .replace(
      '<div id="root"></div>',
      `<div id="root">${body}</div>`,
    )
}

async function main() {
  const template = await readFile(join(DIST, 'index.html'), 'utf8')
  const list = await harbours()
  let written = 0
  const slugs = []
  for (const harbour of list) {
    let detail = null
    try {
      const response = await fetch(`${API}/v1/harbours/${harbour.slug}`)
      if (response.ok) detail = await response.json()
    } catch {
      // A harbour we cannot fetch still gets a minimal indexable page.
    }
    const target = join(DIST, 'port', harbour.slug, 'index.html')
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, shell(template, harbour, detail), 'utf8')
    slugs.push(harbour.slug)
    written += 1
  }
  const urls = ['/', '/contribuer', '/donnees', '/cgu', '/a-propos', ...slugs.map((slug) => `/port/${slug}`)]
  await writeFile(
    join(DIST, 'sitemap.xml'),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls
      .map((url) => `  <url><loc>${url}</loc></url>`)
      .join('\n')}\n</urlset>\n`,
    'utf8',
  )
  console.log(`prerendered ${written} harbour pages + sitemap`)
}

await main()
