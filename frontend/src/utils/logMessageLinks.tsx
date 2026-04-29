import { Link } from 'react-router-dom'
import { imageInspectorPath } from '@/utils/routes'

/** Matches suffix appended by modules/run_log.attach_image_log_suffix */
export const IMAGE_LOG_LINK_TOKEN_RE = /\[\[img:(\d+)\]\]/g

export type ImageLinkSegment =
  | { kind: 'text'; text: string }
  | { kind: 'image'; id: number }

export function splitLogMessageWithImageLinks(message: string): ImageLinkSegment[] {
  if (!message || message.indexOf('[[img:') === -1) {
    return [{ kind: 'text', text: message }]
  }
  const out: ImageLinkSegment[] = []
  let last = 0
  const re = new RegExp(IMAGE_LOG_LINK_TOKEN_RE.source, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(message)) !== null) {
    if (m.index > last) {
      out.push({ kind: 'text', text: message.slice(last, m.index) })
    }
    const id = Number(m[1])
    if (Number.isFinite(id) && id > 0) {
      out.push({ kind: 'image', id })
    } else {
      out.push({ kind: 'text', text: m[0] })
    }
    last = m.index + m[0].length
  }
  if (last < message.length) {
    out.push({ kind: 'text', text: message.slice(last) })
  }
  return out.length ? out : [{ kind: 'text', text: message }]
}

export function LogMessageWithImageLinks({ message }: { message: string }) {
  const segments = splitLogMessageWithImageLinks(message)
  return (
    <>
      {segments.map((s, i) =>
        s.kind === 'text' ? (
          <span key={i}>{s.text}</span>
        ) : (
          <Link
            key={i}
            to={imageInspectorPath(s.id)}
            className="text-[#4fc1ff] underline font-medium hover:text-[#79d4ff]"
            title={`Open image ${s.id}`}
          >
            #{s.id}
          </Link>
        ),
      )}
    </>
  )
}
