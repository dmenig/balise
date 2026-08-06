import { useEffect, useRef, useState } from 'react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { buildStyle } from './style'
import {
  anchoragesLayer,
  boatFilter,
  combineFilters,
  kindFilter,
  spotGlyphLayer,
  spotsLayer,
  visitorOnlyFilter,
} from './layers/spots'
import { navAidLabelsLayer, navAidLitLayer, navAidsLayer } from './layers/navaids'
import { bboxOf, useAppStore } from '../app/store'
import { noLiveUpdates } from './liveUpdates'
import { UserPosition } from './UserPosition'

/** MapLibre is lazy-loaded after the shell paints, to keep first load under budget (docs/09). */
export function MapView(): JSX.Element {
  const container = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const { filters, theme, seamarkOverlay, viewport } = useAppStore()
  const setViewport = useAppStore((state) => state.setViewport)
  const selectSpot = useAppStore((state) => state.selectSpot)
  const selectNavAid = useAppStore((state) => state.selectNavAid)

  useEffect(() => {
    if (!container.current) return
    let instance: MapLibreMap | null = null
    let disposed = false

    void (async () => {
      const maplibre = await import('maplibre-gl')
      if (disposed || !container.current) return
      instance = new maplibre.Map({
        container: container.current,
        style: buildStyle({ night: theme === 'night' }),
        center: [viewport.lon, viewport.lat],
        zoom: viewport.zoom,
        attributionControl: { compact: true },
        hash: false,
      })
      instance.addControl(new maplibre.NavigationControl({ showCompass: true }), 'top-right')
      instance.addControl(new maplibre.ScaleControl({ unit: 'nautical' }), 'bottom-left')

      instance.on('load', () => {
        if (!instance) return
        // Handy for the e2e filter assertion; harmless in production.
        ;(window as unknown as { __baliseMap?: MapLibreMap }).__baliseMap = instance
        instance.addLayer(anchoragesLayer)
        instance.addLayer(navAidLitLayer)
        instance.addLayer(navAidsLayer)
        instance.addLayer(navAidLabelsLayer)
        instance.addLayer(spotsLayer)
        instance.addLayer(spotGlyphLayer)
        setMap(instance)
      })

      instance.on('moveend', () => {
        if (!instance) return
        const center = instance.getCenter()
        setViewport({ lon: center.lng, lat: center.lat, zoom: instance.getZoom() })
      })

      instance.on('click', 'spots', (event) => {
        const feature = event.features?.[0]
        if (feature?.id !== undefined) selectSpot(`spot_${feature.id}`)
      })
      instance.on('click', 'navaids', (event) => {
        const feature = event.features?.[0]
        if (feature?.id !== undefined) selectNavAid(`navaid_${feature.id}`)
      })
      for (const layer of ['spots', 'navaids']) {
        instance.on('mouseenter', layer, () => {
          if (instance) instance.getCanvas().style.cursor = 'pointer'
        })
        instance.on('mouseleave', layer, () => {
          if (instance) instance.getCanvas().style.cursor = ''
        })
      }
    })()

    return () => {
      disposed = true
      instance?.remove()
      setMap(null)
    }
    // The map is created once; theme and filters are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!map) return
    const filter = combineFilters(
      kindFilter(filters.kinds),
      filters.visitorOnly ? visitorOnlyFilter : null,
      boatFilter(filters.draft, filters.loa),
    )
    for (const layer of ['spots', 'spots-glyph']) {
      if (map.getLayer(layer)) map.setFilter(layer, filter)
    }
  }, [map, filters])

  useEffect(() => {
    if (!map || !map.getLayer('seamark')) return
    map.setLayoutProperty('seamark', 'visibility', seamarkOverlay ? 'visible' : 'none')
  }, [map, seamarkOverlay])

  useEffect(() => {
    if (!map) return
    map.setPaintProperty('basemap', 'raster-opacity', theme === 'night' ? 0.35 : 0.9)
    map.setPaintProperty('basemap', 'raster-brightness-max', theme === 'night' ? 0.25 : 0.95)
    map.setPaintProperty('basemap', 'raster-saturation', theme === 'night' ? -1 : -0.4)
  }, [map, theme])

  // The live-update seam (docs/09 S5): v1 subscribes to a no-op, so nothing ever calls
  // `setFeatureState` and every spot stays neutral. v2 swaps the implementation, not the component.
  useEffect(() => {
    if (!map) return
    return noLiveUpdates.subscribe(bboxOf(viewport), () => undefined)
  }, [map, viewport])

  return (
    <div className="relative h-full w-full">
      <div
        ref={container}
        data-testid="map-canvas"
        className="h-full w-full"
        role="application"
        aria-label="Carte des mouillages et du balisage"
      />
      <UserPosition map={map} />
    </div>
  )
}
