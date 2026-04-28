import { defineConfig } from 'vite';
import { resolve } from 'path';

// Game project lives at workspace_dir/game/. We build directly into
// workspace_dir/public/ so the existing /preview proxy serves the game.
export default defineConfig({
  base: './',
  publicDir: 'public',
  build: {
    outDir: resolve(__dirname, '../public'),
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: false,
  },
});
