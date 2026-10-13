import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/antd/',
  build: {
    outDir: '../src/landppt/web/static/antd',
    emptyOutDir: true,
    cssCodeSplit: false,
    manifest: 'manifest.json',
    rolldownOptions: {
      input: { app: 'src/main.tsx', bootstrap: 'src/bootstrap.ts' },
      output: {
        entryFileNames: chunk => chunk.name === 'bootstrap' ? 'app.js' : 'app-[hash].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'app.[ext]',
      },
    },
  },
});
