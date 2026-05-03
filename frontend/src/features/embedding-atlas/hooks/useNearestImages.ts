import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { SimilarImagesResponse } from '@/types/api';

export function useNearestImages(imageId: number | null, limit = 20) {
  return useQuery({
    queryKey: ['nearestImages', imageId, limit],
    queryFn: () =>
      api.get<SimilarImagesResponse>(`/similarity/search?image_id=${imageId}&limit=${limit}`),
    enabled: !!imageId,
    staleTime: 5 * 60 * 1000,
  });
}
