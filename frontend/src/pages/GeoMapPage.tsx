import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  MapPin,
  Search,
  SlidersHorizontal,
  X,
  Loader2,
  Image as ImageIcon,
  Star,
  Camera,
  Calendar,
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-markercluster'
import L from 'leaflet'
import { geoApi, type GeoImage } from '@/api/geo'
import { useUiStore } from '@/stores/uiStore'
import { imageInspectorPath } from '@/utils/routes'

/* ─── Custom marker icon (VS Code accent blue dot) ─── */
function createMarkerIcon(label?: string | null): L.DivIcon {
  const color = label
    ? { Green: '#89d185', Yellow: '#cca700', Red: '#f44747', Blue: '#4fc1ff' }[label] ?? '#007acc'
    : '#007acc'

  return L.divIcon({
    className: 'vx-marker',
    html: `<div style="
      width:12px;height:12px;border-radius:50%;
      background:${color};
      border:2px solid #fff;
      box-shadow:0 0 6px ${color}88;
    "></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -8],
  })
}

/* ─── Custom cluster icon ─── */
function createClusterIcon(cluster: { getChildCount(): number }): L.DivIcon {
  const count = cluster.getChildCount()
  let size = 36
  let fontSize = 12
  let bg = '#007acc'
  if (count >= 100) {
    size = 48; fontSize = 13; bg = '#005999'
  } else if (count >= 10) {
    size = 42; fontSize = 13; bg = '#006bb3'
  }

  return L.divIcon({
    html: `<div class="vx-cluster" style="
      width:${size}px;height:${size}px;
      line-height:${size}px;
      font-size:${fontSize}px;
      background:${bg};
    ">${count}</div>`,
    className: 'vx-cluster-wrapper',
    iconSize: L.point(size, size),
  })
}

/* ─── Map bounds fitter ─── */
function FitBounds({ bounds }: { bounds: { sw: [number, number]; ne: [number, number] } | null }) {
  const map = useMap()
  useEffect(() => {
    if (!bounds) return
    const b = L.latLngBounds(
      L.latLng(bounds.sw[0], bounds.sw[1]),
      L.latLng(bounds.ne[0], bounds.ne[1]),
    )
    map.fitBounds(b, { padding: [40, 40], maxZoom: 14 })
  }, [bounds, map])
  return null
}

/* ─── Thumbnail helper ─── */
function thumbnailSrc(filePath: string): string {
  return `/source-image?path=${encodeURIComponent(filePath)}&thumb=1`
}

/* ─── Label options ─── */
const LABEL_OPTIONS = [
  { value: '', label: 'All labels', color: '' },
  { value: 'Green', label: 'Green', color: '#89d185' },
  { value: 'Yellow', label: 'Yellow', color: '#cca700' },
  { value: 'Red', label: 'Red', color: '#f44747' },
  { value: 'Blue', label: 'Blue', color: '#4fc1ff' },
] as const

/* ─── Rating options ─── */
const RATING_OPTIONS = [
  { value: 0, label: 'Any rating' },
  { value: 1, label: '★ 1+' },
  { value: 2, label: '★★ 2+' },
  { value: 3, label: '★★★ 3+' },
  { value: 4, label: '★★★★ 4+' },
  { value: 5, label: '★★★★★ 5' },
] as const

/* ─── Image Popup Content ─── */
function PopupContent({
  image,
  onClick,
}: {
  image: GeoImage
  onClick: () => void
}) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const fileName = image.file_path.split(/[/\\]/).pop() ?? image.file_path

  return (
    <div className="vx-popup-content">
      <button
        type="button"
        onClick={onClick}
        className="vx-popup-thumb-wrap"
        title="Open in Image Inspector"
      >
        {!error ? (
          <img
            src={thumbnailSrc(image.file_path)}
            alt={fileName}
            loading="lazy"
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
            className={clsx(
              'vx-popup-thumb',
              loaded && 'loaded',
            )}
          />
        ) : (
          <div className="vx-popup-thumb-error">
            <ImageIcon size={20} />
          </div>
        )}
        {!loaded && !error && (
          <div className="vx-popup-thumb-loading">
            <div className="vx-spinner-sm" />
          </div>
        )}
      </button>

      <div className="vx-popup-meta">
        <div className="vx-popup-filename" title={fileName}>{fileName}</div>
        <div className="vx-popup-details">
          {image.camera && (
            <span className="vx-popup-detail">
              <Camera size={10} />
              {image.camera}
            </span>
          )}
          {image.date_taken && (
            <span className="vx-popup-detail">
              <Calendar size={10} />
              {image.date_taken.split('T')[0]}
            </span>
          )}
          {image.rating != null && image.rating > 0 && (
            <span className="vx-popup-detail">
              <Star size={10} />
              {image.rating}
            </span>
          )}
          {image.score_general != null && (
            <span className="vx-popup-detail vx-popup-score">
              {image.score_general.toFixed(1)}
            </span>
          )}
        </div>
        {image.label && (
          <span
            className="vx-popup-label"
            style={{
              background:
                { Green: '#1a3320', Yellow: '#332900', Red: '#3a1515', Blue: '#003f6e' }[image.label] ?? '#252526',
              color:
                { Green: '#89d185', Yellow: '#cca700', Red: '#f44747', Blue: '#4fc1ff' }[image.label] ?? '#9d9d9d',
            }}
          >
            {image.label}
          </span>
        )}
      </div>
    </div>
  )
}

/* ─── Page Component ─── */
export function GeoMapPage() {
  const navigate = useNavigate()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const inputRef = useRef<HTMLInputElement>(null)

  const [keyword, setKeyword] = useState('')
  const [submittedKeyword, setSubmittedKeyword] = useState('')
  const [labelFilter, setLabelFilter] = useState('')
  const [ratingFilter, setRatingFilter] = useState(0)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSearch = useCallback(
    (kw?: string) => {
      setSubmittedKeyword((kw ?? keyword).trim())
    },
    [keyword],
  )

  const handleClear = useCallback(() => {
    setKeyword('')
    setSubmittedKeyword('')
    inputRef.current?.focus()
  }, [])

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['geo-images', submittedKeyword, labelFilter, ratingFilter, selectedScopePath],
    queryFn: () =>
      geoApi.getImages({
        keyword: submittedKeyword || undefined,
        label: labelFilter || undefined,
        rating: ratingFilter || undefined,
        folder_path: selectedScopePath ?? undefined,
        limit: 5000,
      }),
    staleTime: 60_000,
    retry: 1,
  })

  const images = data?.images ?? []
  const bounds = data?.bounds ?? null

  // Memoize markers to avoid Leaflet re-renders
  const markers = useMemo(
    () =>
      images.map((img) => ({
        key: img.image_id,
        position: [img.latitude, img.longitude] as [number, number],
        icon: createMarkerIcon(img.label),
        image: img,
      })),
    [images],
  )

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#1e1e1e]">
      {/* Search / filter bar */}
      <div className="shrink-0 border-b border-[#3c3c3c] bg-[#252526] px-4 py-3">
        <div className="max-w-3xl mx-auto space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleSearch()
            }}
            className="relative"
          >
            <div
              className={clsx(
                'flex items-center gap-2 rounded-lg border bg-[#1e1e1e] px-3 py-2',
                'transition-all duration-200',
                'focus-within:border-[#007acc] focus-within:shadow-[0_0_0_1px_#007acc]',
                !isFetching && 'border-[#474747]',
                isFetching && 'border-[#4fc1ff] shadow-[0_0_0_1px_#4fc1ff]',
              )}
            >
              {isFetching ? (
                <Loader2 size={16} className="text-[#4fc1ff] animate-spin shrink-0" />
              ) : (
                <Search size={16} className="text-[#6d6d6d] shrink-0" />
              )}
              <input
                ref={inputRef}
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Filter by keyword (e.g. bird, sunset)…"
                className={clsx(
                  'flex-1 bg-transparent text-sm text-[#cccccc] placeholder-[#6d6d6d]',
                  'outline-none min-w-0',
                )}
                id="geo-keyword-input"
              />
              {keyword && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="p-0.5 rounded text-[#6d6d6d] hover:text-[#cccccc] transition-colors"
                >
                  <X size={14} />
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowFilters(!showFilters)}
                className={clsx(
                  'p-1 rounded transition-colors',
                  showFilters
                    ? 'text-[#4fc1ff] bg-[#003f6e]'
                    : 'text-[#6d6d6d] hover:text-[#9d9d9d]',
                )}
                title="Map filters"
              >
                <SlidersHorizontal size={14} />
              </button>
              <button
                type="submit"
                disabled={isFetching}
                className={clsx(
                  'px-3 py-1 rounded-md text-xs font-medium transition-all duration-200',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                  'bg-[#007acc] text-white hover:bg-[#1e8ad6] cursor-pointer',
                )}
                id="geo-search-btn"
              >
                Search
              </button>
            </div>
          </form>

          {/* Collapsible filters */}
          {showFilters && (
            <div className="flex flex-wrap items-center gap-4 text-xs text-[#9d9d9d] bg-[#1e1e1e] rounded-lg border border-[#3c3c3c] px-4 py-3">
              <label className="flex items-center gap-2">
                <span className="text-[#6d6d6d]">Label</span>
                <select
                  value={labelFilter}
                  onChange={(e) => setLabelFilter(e.target.value)}
                  className="bg-[#252526] border border-[#474747] rounded px-2 py-1 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
                >
                  {LABEL_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <span className="text-[#6d6d6d]">Rating</span>
                <select
                  value={ratingFilter}
                  onChange={(e) => setRatingFilter(Number(e.target.value))}
                  className="bg-[#252526] border border-[#474747] rounded px-2 py-1 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
                >
                  {RATING_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedScopePath && (
                <div className="flex items-center gap-1">
                  <span className="text-[#6d6d6d]">Scope:</span>
                  <span className="text-[#4fc1ff] truncate max-w-[20rem]" title={selectedScopePath}>
                    {selectedScopePath.split(/[/\\]/).pop()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Map area */}
      <div className="flex-1 min-h-0 relative">
        {isLoading && (
          <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-[#1e1e1e]/80 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-[#3c3c3c] border-t-[#4fc1ff] rounded-full animate-spin" />
              <p className="text-sm text-[#6d6d6d]">Loading map data…</p>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-[#1e1e1e]">
            <div className="flex flex-col items-center gap-2">
              <div className="text-sm text-[#f44747]">Failed to load map data</div>
              <div className="text-xs text-[#9d9d9d]">{(error as Error)?.message ?? 'Unknown error'}</div>
            </div>
          </div>
        )}

        <MapContainer
          center={[30, -97]}
          zoom={4}
          className="h-full w-full"
          zoomControl={true}
          attributionControl={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            maxZoom={20}
          />

          <FitBounds bounds={bounds} />

          <MarkerClusterGroup
            chunkedLoading
            maxClusterRadius={60}
            showCoverageOnHover={false}
            iconCreateFunction={createClusterIcon}
            animate={true}
            spiderfyOnMaxZoom={true}
          >
            {markers.map((m) => (
              <Marker key={m.key} position={m.position} icon={m.icon}>
                <Popup maxWidth={260} minWidth={200} className="vx-map-popup">
                  <PopupContent
                    image={m.image}
                    onClick={() => navigate(imageInspectorPath(m.image.image_id))}
                  />
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>

        {/* Stats badge */}
        <div className="absolute top-3 right-3 z-[1000]">
          <div className="flex items-center gap-1.5 bg-[#252526]/90 backdrop-blur-sm border border-[#3c3c3c] rounded-lg px-3 py-1.5 text-xs shadow-lg">
            <MapPin size={12} className="text-[#4fc1ff]" />
            <span className="text-[#9d9d9d]">
              <span className="text-[#4fc1ff] font-medium">{data?.count ?? 0}</span> photos on map
            </span>
            {isFetching && !isLoading && (
              <Loader2 size={10} className="animate-spin text-[#4fc1ff] ml-1" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
