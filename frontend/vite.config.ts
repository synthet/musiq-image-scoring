import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/** Match an exact npm package path, not every package whose name contains a substring. */
function inNodeModule(id: string, packageName: string): boolean {
  return id.includes(`node_modules/${packageName}/`)
}

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
    // @synthet/image-scoring-design links with its own react@18 devDependency — dedupe to app React 19.
    dedupe: ['react', 'react-dom', 'react/jsx-runtime'],
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
    // Cosmograph WebGL (~2 MB minified) may still exceed this on /embeddings only.
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('node_modules/@cosmograph/')) return 'cosmograph'
          if (
            inNodeModule(id, 'leaflet') ||
            inNodeModule(id, 'react-leaflet') ||
            inNodeModule(id, 'react-leaflet-markercluster')
          ) {
            return 'maps'
          }
          if (inNodeModule(id, '@tanstack/react-query')) return 'query'
          if (inNodeModule(id, 'react-router') || inNodeModule(id, 'react-router-dom')) {
            return 'router'
          }
          if (inNodeModule(id, 'framer-motion')) return 'motion'
          if (inNodeModule(id, 'yet-another-react-lightbox')) return 'lightbox'
          if (
            inNodeModule(id, 'react') ||
            inNodeModule(id, 'react-dom') ||
            inNodeModule(id, 'scheduler')
          ) {
            return 'react'
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
