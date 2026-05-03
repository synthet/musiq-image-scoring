import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cullingApi, type CullingStackImagesResponse } from '../api/culling'
import type { PickStatus } from '../utils/pickStatus'

interface PickArgs {
  imageId: number
  stackId: number
  pickStatus: PickStatus
}

const stackImagesKey = (stackId: number) => ['culling', 'stack-images', stackId] as const

export function usePickMutation() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({ imageId, pickStatus }: PickArgs) =>
      cullingApi.patchPick(imageId, { pick_status: pickStatus }),

    onMutate: async ({ imageId, stackId, pickStatus }) => {
      await qc.cancelQueries({ queryKey: stackImagesKey(stackId) })
      const previous = qc.getQueryData<CullingStackImagesResponse>(stackImagesKey(stackId))
      if (previous) {
        qc.setQueryData<CullingStackImagesResponse>(stackImagesKey(stackId), {
          ...previous,
          images: previous.images.map((img) =>
            img.id === imageId
              ? {
                  ...img,
                  pick_status: pickStatus,
                  rating: pickStatus === 1 ? 4 : pickStatus === -1 ? 1 : 0,
                  label: pickStatus === 1 ? 'Green' : pickStatus === -1 ? 'Red' : '',
                }
              : img,
          ),
        })
      }
      return { previous }
    },

    onError: (_err, vars, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(stackImagesKey(vars.stackId), ctx.previous)
      }
    },

    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({ queryKey: stackImagesKey(vars.stackId) })
      qc.invalidateQueries({ queryKey: ['culling', 'stacks'] })
    },
  })
}
