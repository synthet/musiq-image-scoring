import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

export const FALLBACK_DEFAULT_SPACE_CODE = 'mobilenet_v2_imagenet_gap';

export interface EmbeddingSpace {
  code: string;
  dim: number;
  description: string | null;
  active: boolean;
  is_default: boolean;
}

export interface EmbeddingSpacesData {
  spaces: EmbeddingSpace[];
  meta: {
    default_code: string;
    engine: string;
  };
}

interface RawEnvelope {
  data?: EmbeddingSpacesData;
  spaces?: EmbeddingSpace[];
  meta?: EmbeddingSpacesData['meta'];
}

function unwrap(res: RawEnvelope): EmbeddingSpacesData {
  if (res.data && Array.isArray(res.data.spaces)) return res.data;
  if (Array.isArray(res.spaces)) {
    return {
      spaces: res.spaces,
      meta: res.meta ?? { default_code: FALLBACK_DEFAULT_SPACE_CODE, engine: 'unknown' },
    };
  }
  return {
    spaces: [],
    meta: { default_code: FALLBACK_DEFAULT_SPACE_CODE, engine: 'unknown' },
  };
}

export function useEmbeddingSpaces() {
  return useQuery({
    queryKey: ['embeddingSpaces'],
    queryFn: async () => {
      const res = await api.get<RawEnvelope>('/embedding_spaces');
      return unwrap(res);
    },
    staleTime: Infinity,
  });
}

export function resolveDefaultSpaceCode(data: EmbeddingSpacesData | undefined): string {
  if (!data) return FALLBACK_DEFAULT_SPACE_CODE;
  if (data.meta?.default_code) return data.meta.default_code;
  const flagged = data.spaces.find((s) => s.is_default);
  if (flagged) return flagged.code;
  if (data.spaces.length > 0) return data.spaces[0].code;
  return FALLBACK_DEFAULT_SPACE_CODE;
}
