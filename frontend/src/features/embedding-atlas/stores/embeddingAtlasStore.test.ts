import { describe, expect, it, beforeEach } from 'vitest';
import { useEmbeddingAtlasStore } from './embeddingAtlasStore';

describe('embeddingAtlasStore', () => {
  beforeEach(() => {
    useEmbeddingAtlasStore.setState({
      hoveredPointId: null,
      selectedPointId: null,
      currentTool: 'pointer',
      activeColorMode: 'folder',
      sidePanelOpen: false,
      selectedClusterIds: [],
    });
  });

  it('does not close the inspector preference when clearing selection', () => {
    const { setSelectedPointId, setSidePanelOpen } = useEmbeddingAtlasStore.getState();

    setSelectedPointId(42);
    setSidePanelOpen(true);
    setSelectedPointId(null);

    expect(useEmbeddingAtlasStore.getState()).toMatchObject({
      selectedPointId: null,
      sidePanelOpen: true,
    });
  });
});
