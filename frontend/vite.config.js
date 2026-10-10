import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the browser talks to Vite, and Vite forwards /api/* to the FastAPI server,
// so no CORS configuration is needed. For a deployed build, serve both behind one origin
// (for example nginx) or add CORS middleware to the API.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.js",
    globals: true,
  },
});
