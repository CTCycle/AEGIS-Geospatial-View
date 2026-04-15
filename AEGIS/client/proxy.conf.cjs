const fs = require('node:fs');
const path = require('node:path');

const settingsEnvPath = path.resolve(__dirname, '../settings/.env');

const parseEnvFile = (filePath) => {
  if (!fs.existsSync(filePath)) {
    return {};
  }
  const content = fs.readFileSync(filePath, 'utf8');
  const entries = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }
    const eqIndex = line.indexOf('=');
    if (eqIndex <= 0) {
      continue;
    }
    const key = line.slice(0, eqIndex).trim();
    const value = line.slice(eqIndex + 1).trim();
    entries[key] = value;
  }
  return entries;
};

const envFromSettings = parseEnvFile(settingsEnvPath);
const apiHost = process.env.FASTAPI_HOST || envFromSettings.FASTAPI_HOST || '127.0.0.1';
const apiPort = process.env.FASTAPI_PORT || envFromSettings.FASTAPI_PORT || '5002';
const apiTarget = `http://${apiHost}:${apiPort}`;

module.exports = {
  '/api': {
    target: apiTarget,
    secure: false,
    changeOrigin: true,
    pathRewrite: {
      '^/api': '',
    },
  },
};
