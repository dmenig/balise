import { useEffect, useState } from 'react'
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import { useAppStore } from '../app/store'

/** Position is computed client-side and never sent to the server (docs/04 §4). */
export function UserPosition({ map }: { map: MapLibreMap | null }): JSX.Element | null {
  const [position, setPosition] = useState<GeolocationPosition | null>(null)
  const [denied, setDenied] = useState(false)
  const publish = useAppStore((state) => state.setPosition)

  useEffect(() => {
    if (!navigator.geolocation) return
    const id = navigator.geolocation.watchPosition(
      (next) => {
        setPosition(next)
        publish([next.coords.longitude, next.coords.latitude])
      },
      () => setDenied(true),
      { enableHighAccuracy: true, maximumAge: 10_000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [publish])

  useEffect(() => {
    if (!map || !position) return
    const source = 'user-position'
    const data: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [position.coords.longitude, position.coords.latitude],
          },
          properties: { accuracy: position.coords.accuracy, heading: position.coords.heading ?? 0 },
        },
      ],
    }
    const existing = map.getSource(source)
    if (existing && 'setData' in existing) {
      const geojson = existing as GeoJSONSource
      geojson.setData(data)
      return
    }
    map.addSource(source, { type: 'geojson', data })
    map.addLayer({
      id: 'user-accuracy',
      type: 'circle',
      source,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 6, 17, 26],
        'circle-color': '#3d7f9e',
        'circle-opacity': 0.2,
      },
    })
    map.addLayer({
      id: 'user-dot',
      type: 'circle',
      source,
      paint: {
        'circle-radius': 6,
        'circle-color': '#0b2b3c',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff',
      },
    })
  }, [map, position])

  if (denied) {
    return (
      <p className="pointer-events-none absolute bottom-24 left-2 rounded bg-white/90 px-2 py-1 text-xs text-sea-900">
        Position refusée — la carte reste utilisable, recherchez un port.
      </p>
    )
  }
  return null
}
