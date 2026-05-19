import { describe, expect, it } from 'vitest';
import {
  FALLBACK_DEFAULT_SPACE_CODE,
  resolveDefaultSpaceCode,
  type EmbeddingSpacesData,
} from './useEmbeddingSpaces';

describe('resolveDefaultSpaceCode', () => {
  it('falls back when data is undefined', () => {
    expect(resolveDefaultSpaceCode(undefined)).toBe(FALLBACK_DEFAULT_SPACE_CODE);
  });

  it('prefers meta.default_code when present', () => {
    const data: EmbeddingSpacesData = {
      spaces: [
        { code: 'clip_vit_b32_image', dim: 512, description: 'CLIP', active: true, is_default: false },
      ],
      meta: { default_code: 'clip_vit_b32_image', engine: 'postgres' },
    };
    expect(resolveDefaultSpaceCode(data)).toBe('clip_vit_b32_image');
  });

  it('uses the is_default flag when meta is empty', () => {
    const data: EmbeddingSpacesData = {
      spaces: [
        { code: 'a', dim: 256, description: null, active: true, is_default: false },
        { code: 'b', dim: 512, description: null, active: true, is_default: true },
      ],
      meta: { default_code: '', engine: 'postgres' },
    };
    expect(resolveDefaultSpaceCode(data)).toBe('b');
  });

  it('falls back to first space when nothing is flagged', () => {
    const data: EmbeddingSpacesData = {
      spaces: [
        { code: 'first', dim: 256, description: null, active: true, is_default: false },
        { code: 'second', dim: 512, description: null, active: true, is_default: false },
      ],
      meta: { default_code: '', engine: 'postgres' },
    };
    expect(resolveDefaultSpaceCode(data)).toBe('first');
  });

  it('falls back to MobileNetV2 when the registry is empty', () => {
    const data: EmbeddingSpacesData = {
      spaces: [],
      meta: { default_code: '', engine: 'firebird' },
    };
    expect(resolveDefaultSpaceCode(data)).toBe(FALLBACK_DEFAULT_SPACE_CODE);
  });
});
