import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { bboxOf, useAppStore } from '../../app/store'
import type { FeatureCollection } from '../../lib/types'

/**
 * The spots in the current view, shared by the list and its handle. One query key, so TanStack
 * dedupes it and the count on the handle can never disagree with the rows underneath it.
 */
export function useSpotsInView() {
  const viewport = useAppStore((state) => state.viewport)
  const filters = useAppStore((state) => state.filters)
  const bbox = bboxOf(viewport)

  return useQuery<FeatureCollection>({
    queryKey: ['spots', bbox, filters],
    queryFn: () =>
      api.spots({
        bbox,
        ...(filters.kinds.length ? { kind: filters.kinds.join(',') } : {}),
        ...(filters.visitorOnly ? { visitor: true } : {}),
        ...(filters.draft ? { max_draft_m: filters.draft } : {}),
        ...(filters.loa ? { max_loa_m: filters.loa } : {}),
        ...(filters.shelteredFrom.length
          ? { sheltered_from: filters.shelteredFrom.join(',') }
          : {}),
        limit: 100,
      }),
    staleTime: 15_000,
  })
}
