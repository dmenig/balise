/**
 * "Télécharger cette zone" (docs/09 offline strategy): warm the tile caches for a 20 NM radius
 * so the area stays readable with no signal. Explicit, never a background data grab.
 */
import { useState } from 'react'
import { tileUrl } from '../../lib/api'
import { bboxOf, useAppStore } from '../../app/store'

const RADIUS_NM = 20
/**
 * 20 NM of overview, tapering with zoom: a full 20 NM at z14 is ~2 400 tiles and tens of MB on a
 * phone, and MapLibre overzooms z13 to keep the outer ring readable anyway (docs/09).
 */
const ZOOM_RADIUS_NM: Record<number, number> = { 11: RADIUS_NM, 12: RADIUS_NM, 13: 10, 14: 5 }

function tilesFor(lon: number, lat: number, zoom: number, radiusNm: number): [number, number][] {
  const degrees = radiusNm / 60
  const n = 2 ** zoom
  const xOf = (longitude: number) => Math.floor(((longitude + 180) / 360) * n)
  const yOf = (latitude: number) => {
    const rad = (latitude * Math.PI) / 180
    return Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n)
  }
  const tiles: [number, number][] = []
  for (let x = xOf(lon - degrees); x <= xOf(lon + degrees); x += 1) {
    for (let y = yOf(lat + degrees); y <= yOf(lat - degrees); y += 1) {
      if (x >= 0 && y >= 0 && x < n && y < n) tiles.push([x, y])
    }
  }
  return tiles
}

export function DownloadArea(): JSX.Element {
  const viewport = useAppStore((state) => state.viewport)
  const [progress, setProgress] = useState<number | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const download = async () => {
    setDone(null)
    const jobs: string[] = []
    for (const [zoom, radius] of Object.entries(ZOOM_RADIUS_NM)) {
      for (const [x, y] of tilesFor(viewport.lon, viewport.lat, Number(zoom), radius)) {
        for (const layer of ['navaids', 'spots'] as const) {
          jobs.push(
            tileUrl(layer).replace('{z}', zoom).replace('{x}', String(x)).replace('{y}', String(y)),
          )
        }
      }
    }
    // Also warm the sheets for the visible spots so they are readable offline.
    jobs.push(`/v1/spots?bbox=${bboxOf(viewport)}&limit=100`)

    let completed = 0
    const concurrency = 6
    const queue = [...jobs]
    const workers = Array.from({ length: concurrency }, async () => {
      while (queue.length) {
        const next = queue.shift()
        if (!next) return
        try {
          await fetch(next, { cache: 'reload' })
        } catch {
          /* one missing tile must not abort the download */
        }
        completed += 1
        setProgress(Math.round((completed / jobs.length) * 100))
      }
    })
    await Promise.all(workers)
    setProgress(null)
    setDone(`${jobs.length} tuiles et fiches en cache pour ${RADIUS_NM} NM autour de la vue.`)
  }

  return (
    <div className="px-3 py-2">
      <button
        type="button"
        data-testid="download-area"
        onClick={() => void download()}
        disabled={progress !== null}
        className="h-touch w-full rounded-xl border-2 border-sea-700 text-sm font-semibold text-sea-900 disabled:opacity-60"
      >
        {progress === null
          ? `Télécharger cette zone (${RADIUS_NM} NM)`
          : `Téléchargement ${progress} %`}
      </button>
      {done && (
        <p data-testid="download-done" role="status" className="mt-1 text-xs text-sea-700">
          {done}
        </p>
      )}
    </div>
  )
}
