import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8000);
const BACKEND_URL = process.env.BACKEND_URL ?? `http://127.0.0.1:${BACKEND_PORT}`;

function portInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host: "127.0.0.1" });
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("error", () => resolve(false));
  });
}

// Levanta el backend junto con `npm run dev`, para no tener que abrir otra terminal.
// Si el backend ya está corriendo (o se definió BACKEND_URL), no hace nada.
function startBackend(): Plugin {
  let child: ChildProcess | null = null;
  return {
    name: "neumavision-backend",
    apply: "serve",
    async configureServer() {
      if (process.env.BACKEND_URL || (await portInUse(BACKEND_PORT))) return;
      const backendDir = path.resolve(__dirname, "../backend");
      const python = ["venv", ".venv"]
        .map((dir) => path.join(backendDir, dir, process.platform === "win32" ? "Scripts/python.exe" : "bin/python"))
        .find((candidate) => existsSync(candidate));
      if (!python) {
        console.warn("[backend] No se encontró backend/venv. Crea el entorno virtual e instala requirements.txt.");
        return;
      }
      console.log(`[backend] Iniciando API en ${BACKEND_URL}`);
      child = spawn(python, ["-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)], {
        cwd: backendDir,
        stdio: "inherit"
      });
      const stop = () => { child?.kill(); child = null; };
      process.once("exit", stop);
      process.once("SIGINT", () => { stop(); process.exit(0); });
      process.once("SIGTERM", () => { stop(); process.exit(0); });
    }
  };
}

export default defineConfig({
  plugins: [react(), startBackend()],
  server: {
    port: 5173,
    proxy: {
      "/api": BACKEND_URL
    }
  },
  preview: {
    proxy: {
      "/api": BACKEND_URL
    }
  }
});
