import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/antd/',
  build: {
    outDir: '../src/landppt/web/static/antd',
    emptyOutDir: true,
    cssCodeSplit: false,
    rolldownOptions: {
      input: 'src/main.tsx',
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'app.[ext]',
      },
    },
  },
});
