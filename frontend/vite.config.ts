import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "DPO_");
  return {
    server: {
      port: Number(env.DPO_FRONTEND_PORT || 5173),
      strictPort: true,
      proxy: { "/api": env.DPO_API_TARGET || "http://127.0.0.1:8000" },
    },
    preview: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": "http://127.0.0.1:8000" },
    },
  };
});
