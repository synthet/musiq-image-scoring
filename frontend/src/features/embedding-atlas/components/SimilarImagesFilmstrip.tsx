import { useNearestImages } from '../hooks/useNearestImages';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import { Virtuoso } from 'react-virtuoso';

export function SimilarImagesFilmstrip() {
  const selectedPointId = useEmbeddingAtlasStore((s) => s.selectedPointId);
  const setSelectedPointId = useEmbeddingAtlasStore((s) => s.setSelectedPointId);

  const { data, isLoading } = useNearestImages(selectedPointId, 50);

  if (!selectedPointId) return null;

  return (
    <div className="h-full w-full bg-slate-950 border-t border-slate-800 p-2">
      <div className="mb-2 px-2 text-xs font-medium text-slate-400">
        Similar Images
      </div>
      <div className="h-[calc(100%-24px)] w-full">
        {isLoading ? (
          <div className="flex h-full items-center px-4 text-sm text-slate-500">Loading...</div>
        ) : !data?.results?.length ? (
          <div className="flex h-full items-center px-4 text-sm text-slate-500">No similar images found.</div>
        ) : (
          <Virtuoso
            horizontalDirection
            data={data.results}
            className="h-full w-full custom-scrollbar"
            itemContent={(_index, item) => (
              <div
                className="h-full px-1 cursor-pointer"
                onClick={() => setSelectedPointId(item.image_id)}
              >
                <img
                  src={`/api/images/${item.image_id}/thumbnail`}
                  alt={item.file_path}
                  className="h-full max-w-[120px] object-cover rounded-md border border-slate-800 hover:border-slate-400 transition-colors"
                  title={`${item.file_path.split(/[/\\]/).pop()} (Sim: ${(item.similarity * 100).toFixed(1)}%)`}
                />
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
}
