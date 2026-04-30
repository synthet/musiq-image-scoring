import * as Dialog from '@radix-ui/react-dialog';
import { Settings, X } from 'lucide-react';
import type { FetchEmbeddingMapParams } from '../hooks/useEmbeddingMap';

interface ProjectionSettingsDialogProps {
  params: FetchEmbeddingMapParams;
  setParams: (params: FetchEmbeddingMapParams) => void;
  onRefresh: () => void;
}

export function ProjectionSettingsDialog({ params, setParams, onRefresh }: ProjectionSettingsDialogProps) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button className="flex items-center gap-2 rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-slate-700">
          <Settings className="h-4 w-4" />
          Settings
        </button>
      </Dialog.Trigger>
      
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed left-[50%] top-[50%] max-h-[85vh] w-[90vw] max-w-[450px] translate-x-[-50%] translate-y-[-50%] rounded-xl bg-slate-900 p-6 shadow-[hsl(206_22%_7%_/_35%)_0px_10px_38px_-10px,_hsl(206_22%_7%_/_20%)_0px_10px_20px_-15px] focus:outline-none z-50 border border-slate-700">
          <div className="flex justify-between items-center mb-5">
            <Dialog.Title className="text-lg font-semibold text-slate-100">
              Projection Settings
            </Dialog.Title>
            <Dialog.Close asChild>
              <button className="text-slate-400 hover:text-slate-100" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>
          
          <div className="space-y-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-300" htmlFor="spaceCode">
                Embedding Space
              </label>
              <select 
                id="spaceCode" 
                className="rounded bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
                value={params.space_code || 'mobilenet_v2_imagenet_gap'}
                onChange={(e) => setParams({ ...params, space_code: e.target.value })}
              >
                <option value="mobilenet_v2_imagenet_gap">MobileNetV2 (1280d)</option>
                <option value="clip_vit_b32_image">CLIP ViT-B/32 (512d)</option>
                <option value="blip_vit_b16_image">BLIP ViT-B/16 (256d)</option>
                <option value="bioclip_2_image">BioCLIP 2 (512d)</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-slate-300" htmlFor="method">
                Method
              </label>
              <select 
                id="method" 
                className="rounded bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
                value={params.method || 'umap'}
                onChange={(e) => setParams({ ...params, method: e.target.value as 'umap' | 'tsne' })}
              >
                <option value="umap">UMAP</option>
                <option value="tsne">t-SNE</option>
              </select>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Dialog.Close asChild>
                <button className="rounded px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800">
                  Close
                </button>
              </Dialog.Close>
              <button 
                onClick={() => {
                  onRefresh();
                  // Ideally close dialog here too
                }}
                className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Re-Project
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
