import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

// https://vite.dev/config/
const settingsEnvPath = path.resolve(__dirname, '../settings/.env')

const parseEnvFile = (filePath: string): Record<string, string> => {
    if (!fs.existsSync(filePath)) {
        return {}
    }
    const content = fs.readFileSync(filePath, 'utf8')
    const lines = content.split(/\r?\n/)
    const entries: Record<string, string> = {}
    for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line || line.startsWith('#')) {
            continue
        }
        const eqIndex = line.indexOf('=')
        if (eqIndex <= 0) {
            continue
        }
        const key = line.slice(0, eqIndex).trim()
        const value = line.slice(eqIndex + 1).trim()
        entries[key] = value
    }
    return entries
}

const envFromSettings = parseEnvFile(settingsEnvPath)
const apiHost = process.env.FASTAPI_HOST || envFromSettings.FASTAPI_HOST || '127.0.0.1'
const apiPort = process.env.FASTAPI_PORT || envFromSettings.FASTAPI_PORT || '5002'
const apiTarget = `http://${apiHost}:${apiPort}`


export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 7861,
        strictPort: false,
        proxy: {
            '/api': {
                target: apiTarget,
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ''),
            },
        },
    },
    preview: {
        host: '127.0.0.1',
        port: 7861,
        strictPort: false,
        proxy: {
            '/api': {
                target: apiTarget,
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ''),
            },
        },
    },
})
