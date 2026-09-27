import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the API, so there is no CORS setup.
// Point it at a different instance with API_PORT=8001 npm run dev.
const apiPort = process.env.API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${apiPort}`,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
