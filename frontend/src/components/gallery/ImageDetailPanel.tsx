import { clsx } from 'clsx'
import { Star } from 'lucide-react'
import { LabelBadge } from '@/components/images/InspectorPrimitives'
import type { Image } from '@/types/api'

export function ImageDetailContent({ image }: { image: Image }) {
  const keywords = image.keywords
    ? image.keywords.split(',').map((k) => k.trim()).filter(Boolean)
    : []

  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
          Quality Scores
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: 'General', value: image.score_general },
            { label: 'Technical', value: image.score_technical },
            { label: 'Aesthetic', value: image.score_aesthetic },
            { label: 'LIQE', value: image.score_liqe },
          ].map(({ label, value }) => (
            <ScoreCell key={label} label={label} value={value} />
          ))}
        </div>
        {(image.musiq_score != null || image.topiq_score != null || image.qalign_score != null) && (
          <div className="grid grid-cols-2 gap-2 mt-2">
            {[
              { label: 'MUSIQ', value: image.musiq_score },
              { label: 'TOPIQ-NR', value: image.topiq_score },
              { label: 'Q-Align', value: image.qalign_score },
            ]
              .filter(({ value }) => value != null)
              .map(({ label, value }) => (
                <ScoreCell key={label} label={label} value={value} />
              ))}
          </div>
        )}
        {image.composite_score != null && (
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-[#9d9d9d]">Composite</span>
            <span className="text-sm font-bold text-[#4fc1ff]">
              {(image.composite_score * 100).toFixed(1)}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Rating</div>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <Star
                key={r}
                size={16}
                className={clsx(
                  'cursor-pointer transition-colors',
                  r <= (image.rating ?? 0) ? 'text-[#cca700] fill-[#cca700]' : 'text-[#474747]',
                )}
              />
            ))}
          </div>
        </div>

        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Label</div>
          <LabelBadge label={image.label} />
        </div>
      </div>

      {keywords.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Keywords</div>
          <div className="flex flex-wrap gap-1">
            {keywords.map((kw) => (
              <span
                key={kw}
                className="bg-[#3c3c3c] text-[#9d9d9d] text-xs px-2 py-0.5 rounded border border-[#474747]"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {image.file_type && <div className="text-xs text-[#6d6d6d]">{image.file_type}</div>}
    </div>
  )
}

function ScoreCell({ label, value }: { label: string; value: number | null | undefined }) {
  const display =
    value != null ? (value > 1 ? value.toFixed(1) : `${(value * 100).toFixed(1)}%`) : '—'
  return (
    <div className="bg-[#1e1e1e] rounded p-2 border border-[#3c3c3c]">
      <div className="text-[10px] text-[#6d6d6d]">{label}</div>
      <div className="text-sm font-semibold text-[#cccccc]">{display}</div>
    </div>
  )
}
