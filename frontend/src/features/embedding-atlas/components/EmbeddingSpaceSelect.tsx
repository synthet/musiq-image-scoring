import { useMemo } from 'react';
import { clsx } from 'clsx';
import {
  EmbeddingSpaceIcon,
  EMBEDDING_SPACE_LABELS,
} from '@synthet/image-scoring-design';
import type { EmbeddingSpace } from '../hooks/useEmbeddingSpaces';

function formatSpaceLabel(space: EmbeddingSpace): string {
  const fromDesign = EMBEDDING_SPACE_LABELS[space.code];
  if (fromDesign) return fromDesign;
  const base = space.description?.trim() || space.code;
  return `${base} (${space.dim}d)`;
}

export function EmbeddingSpaceSelect({
  spaces,
  selectedCode,
  disabled,
  onChange,
  unknownSelectedLabel,
}: {
  spaces: EmbeddingSpace[];
  selectedCode: string;
  disabled?: boolean;
  onChange: (code: string) => void;
  unknownSelectedLabel?: string;
}) {
  const options = useMemo(() => {
    const list = spaces.map((s) => ({
      code: s.code,
      label: formatSpaceLabel(s),
      isDefault: !!s.is_default,
    }));
    if (unknownSelectedLabel && !list.some((o) => o.code === selectedCode)) {
      list.push({
        code: selectedCode,
        label: unknownSelectedLabel,
        isDefault: false,
      });
    }
    return list;
  }, [spaces, selectedCode, unknownSelectedLabel]);

  if (disabled && options.length === 0) {
    return (
      <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-400">
        Loading…
      </div>
    );
  }

  return (
    <div
      className="flex max-h-52 flex-col gap-0.5 overflow-y-auto rounded border border-slate-700 bg-slate-950 p-1"
      role="listbox"
      aria-label="Embedding space"
    >
      {options.map((opt) => {
        const selected = opt.code === selectedCode;
        return (
          <button
            key={opt.code}
            type="button"
            role="option"
            aria-selected={selected}
            disabled={disabled}
            onClick={() => onChange(opt.code)}
            className={clsx(
              'flex items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition-colors',
              selected ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-800/60',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            <EmbeddingSpaceIcon code={opt.code} size={16} />
            <span className="min-w-0 flex-1 truncate">{opt.label}</span>
            {opt.isDefault ? (
              <span className="shrink-0 text-xs text-slate-500">default</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function EmbeddingSpaceLegend({ code, label }: { code: string; label?: string }) {
  const text = label ?? EMBEDDING_SPACE_LABELS[code] ?? code;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-slate-300">
      <EmbeddingSpaceIcon code={code} size={16} />
      <span className="truncate">{text}</span>
    </span>
  );
}
