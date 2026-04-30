import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  base: '/ui/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      'gl-bench': path.resolve(__dirname, './src/mocks/gl-bench.ts'),
    },
  },
  optimizeDeps: {
    include: ['gl-bench', '@cosmograph/react'],
  },
  build: {
    commonjsOptions: {
      transformMixedEsModules: true,
      include: [/gl-bench/, /node_modules/],
    },
    outDir: '../static/app',
    emptyOutDir: true,
    // Vite warns at 500 kB; our UI can legitimately exceed this (e.g. Leaflet/map).
    // Keep the warning, but reduce noise and split known heavy deps.
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('react') || id.includes('react-dom')) return 'react'
          if (id.includes('react-router-dom')) return 'router'
          if (id.includes('@tanstack/react-query')) return 'query'
          if (
            id.includes('leaflet') ||
            id.includes('react-leaflet') ||
            id.includes('react-leaflet-markercluster')
          ) {
            return 'maps'
          }
        },
      },
    },
  },
  server: {
    proxy: {
      '/favicon.png': 'http://localhost:7860',
      '/favicon.ico': 'http://localhost:7860',
      '/api': 'http://localhost:7860',
      '/public/api': 'http://localhost:7860',
      '/ws': {
        target: 'ws://localhost:7860',
        ws: true,
      },
      '/source-image': 'http://localhost:7860',
    },
  },
})
