const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const BUILD_SCHEMA_VERSION = 1;
const DEPENDENCY_SCHEMA_VERSION = 1;
const CURRENT = 0;
const EVALUATION_ERROR = 1;
const MISSING = 2;
const STALE = 3;
const BUILD_MARKER = path.join('dist', '.aegis-build-state.json');
const DEPENDENCY_MARKER = path.join('node_modules', '.aegis-dependency-state.json');
const BUILD_INPUT_FILES = [
  'angular.json',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  'tsconfig.app.json',
  '.nvmrc',
];
const DEPENDENCY_FIELDS = [
  'dependencies',
  'devDependencies',
  'optionalDependencies',
  'peerDependencies',
  'peerDependenciesMeta',
  'bundledDependencies',
  'overrides',
  'workspaces',
  'engines',
  'packageManager',
];

function comparePaths(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function walkFiles(directory, projectRoot) {
  if (!fs.existsSync(directory)) return [];
  const files = [];
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  entries.sort((left, right) => comparePaths(left.name, right.name));
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(absolutePath, projectRoot));
    } else if (entry.isFile()) {
      files.push({
        absolutePath,
        relativePath: path.relative(projectRoot, absolutePath).split(path.sep).join('/'),
      });
    }
  }
  return files;
}

function hashEntries(entries) {
  const hash = crypto.createHash('sha256');
  entries.sort((left, right) => comparePaths(left.relativePath, right.relativePath));
  for (const entry of entries) {
    const content = entry.content;
    hash.update(entry.relativePath, 'utf8');
    hash.update('\0', 'utf8');
    hash.update(String(content.length), 'utf8');
    hash.update('\0', 'utf8');
    hash.update(content);
    hash.update('\0', 'utf8');
  }
  return hash.digest('hex');
}

function hashFiles(files) {
  return hashEntries(
    files.map((file) => ({
      relativePath: file.relativePath,
      content: fs.existsSync(file.absolutePath)
        ? fs.readFileSync(file.absolutePath)
        : Buffer.from('<missing>', 'utf8'),
    })),
  );
}

function collectBuildInputs(projectRoot) {
  const entries = [];
  const sourceRoot = path.join(projectRoot, 'src');
  for (const file of walkFiles(sourceRoot, projectRoot)) {
    const sourceRelativePath = path.relative(sourceRoot, file.absolutePath).split(path.sep).join('/');
    if (/\.spec\.ts$/i.test(sourceRelativePath)) continue;
    if (sourceRelativePath === 'test.ts' || sourceRelativePath.startsWith('app/e2e/')) continue;
    entries.push(file);
  }
  entries.push(...walkFiles(path.join(projectRoot, 'public'), projectRoot));
  for (const relativePath of BUILD_INPUT_FILES) {
    const absolutePath = path.join(projectRoot, relativePath);
    entries.push({ absolutePath, relativePath });
  }
  return entries;
}

function buildInputHash(projectRoot) {
  return hashFiles(collectBuildInputs(projectRoot));
}

function outputHash(projectRoot) {
  const browserRoot = path.join(projectRoot, 'dist', 'browser');
  return hashFiles(walkFiles(browserRoot, browserRoot));
}

function markerPath(projectRoot, relativePath) {
  return path.join(projectRoot, relativePath);
}

function readMarker(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    if (error && error.code === 'ENOENT') return null;
    if (error instanceof SyntaxError) return { malformed: true };
    throw error;
  }
}

function writeMarker(filePath, value) {
  const temporaryPath = `${filePath}.${process.pid}.${crypto.randomBytes(6).toString('hex')}.tmp`;
  try {
    fs.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
    fs.renameSync(temporaryPath, filePath);
  } finally {
    fs.rmSync(temporaryPath, { force: true });
  }
}

function invalidateBuild(projectRoot) {
  fs.rmSync(markerPath(projectRoot, BUILD_MARKER), { force: true });
}

function recordBuild(projectRoot, nodeVersion = process.version) {
  const indexPath = path.join(projectRoot, 'dist', 'browser', 'index.html');
  if (!fs.existsSync(indexPath) || !fs.statSync(indexPath).isFile()) {
    throw new Error(`Production build entrypoint is missing: ${indexPath}`);
  }
  const value = {
    schemaVersion: BUILD_SCHEMA_VERSION,
    inputSha256: buildInputHash(projectRoot),
    outputSha256: outputHash(projectRoot),
    nodeVersion,
  };
  const filePath = markerPath(projectRoot, BUILD_MARKER);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  writeMarker(filePath, value);
}

function getBuildState(projectRoot, nodeVersion = process.version) {
  const filePath = markerPath(projectRoot, BUILD_MARKER);
  const browserRoot = path.join(projectRoot, 'dist', 'browser');
  const indexPath = path.join(browserRoot, 'index.html');
  if (!fs.existsSync(indexPath) || !fs.statSync(indexPath).isFile()) {
    return { status: 'Missing', reason: 'production output is missing' };
  }
  if (!fs.existsSync(filePath)) {
    return { status: 'Missing', reason: 'build marker is missing' };
  }
  const marker = readMarker(filePath);
  if (!marker || marker.malformed) {
    return { status: 'Stale', reason: 'build marker is malformed' };
  }
  if (marker.schemaVersion !== BUILD_SCHEMA_VERSION) {
    return { status: 'Stale', reason: 'build marker schema is unsupported' };
  }
  if (marker.nodeVersion !== nodeVersion) {
    return { status: 'Stale', reason: 'Node runtime version changed' };
  }
  if (marker.inputSha256 !== buildInputHash(projectRoot)) {
    return { status: 'Stale', reason: 'production build inputs changed' };
  }
  if (marker.outputSha256 !== outputHash(projectRoot)) {
    return { status: 'Stale', reason: 'generated production output changed' };
  }
  return { status: 'Current', reason: 'inputs and output match the recorded build' };
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort(comparePaths);
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function dependencyInputHash(projectRoot, nodeVersion = process.version) {
  const packagePath = path.join(projectRoot, 'package.json');
  const lockPath = path.join(projectRoot, 'package-lock.json');
  const nodeVersionPath = path.join(projectRoot, '.nvmrc');
  for (const requiredPath of [packagePath, lockPath, nodeVersionPath]) {
    if (!fs.existsSync(requiredPath) || !fs.statSync(requiredPath).isFile()) {
      throw new Error(`Required frontend dependency input is missing: ${requiredPath}`);
    }
  }
  const packageManifest = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  const dependencyFields = {};
  for (const field of DEPENDENCY_FIELDS) {
    if (Object.hasOwn(packageManifest, field)) dependencyFields[field] = packageManifest[field];
  }
  const nodeModulesRoot = path.join(projectRoot, 'node_modules');
  const npmHiddenLock = path.join(nodeModulesRoot, '.package-lock.json');
  const entries = [
    { relativePath: 'package.json:dependency-fields', content: Buffer.from(stableJson(dependencyFields), 'utf8') },
    { relativePath: 'package-lock.json', content: fs.readFileSync(lockPath) },
    { relativePath: '.nvmrc', content: fs.readFileSync(nodeVersionPath) },
    { relativePath: 'node-version', content: Buffer.from(nodeVersion, 'utf8') },
    {
      relativePath: 'node_modules/.package-lock.json',
      content: fs.existsSync(npmHiddenLock)
        ? fs.readFileSync(npmHiddenLock)
        : Buffer.from('<missing>', 'utf8'),
    },
  ];
  return hashEntries(entries);
}

function invalidateDependencies(projectRoot) {
  fs.rmSync(markerPath(projectRoot, DEPENDENCY_MARKER), { force: true });
}

function recordDependencies(projectRoot, nodeVersion = process.version) {
  const nodeModulesRoot = path.join(projectRoot, 'node_modules');
  if (!fs.existsSync(nodeModulesRoot) || !fs.statSync(nodeModulesRoot).isDirectory()) {
    throw new Error(`Frontend dependency directory is missing: ${nodeModulesRoot}`);
  }
  const value = {
    schemaVersion: DEPENDENCY_SCHEMA_VERSION,
    inputSha256: dependencyInputHash(projectRoot, nodeVersion),
    nodeVersion,
  };
  writeMarker(markerPath(projectRoot, DEPENDENCY_MARKER), value);
}

function getDependencyState(projectRoot, nodeVersion = process.version) {
  const nodeModulesRoot = path.join(projectRoot, 'node_modules');
  const filePath = markerPath(projectRoot, DEPENDENCY_MARKER);
  if (!fs.existsSync(nodeModulesRoot) || !fs.statSync(nodeModulesRoot).isDirectory()) {
    return { status: 'Missing', reason: 'node_modules is missing' };
  }
  if (!fs.existsSync(filePath)) {
    return { status: 'Missing', reason: 'dependency marker is missing' };
  }
  const marker = readMarker(filePath);
  if (!marker || marker.malformed) {
    return { status: 'Stale', reason: 'dependency marker is malformed' };
  }
  if (marker.schemaVersion !== DEPENDENCY_SCHEMA_VERSION) {
    return { status: 'Stale', reason: 'dependency marker schema is unsupported' };
  }
  if (marker.nodeVersion !== nodeVersion) {
    return { status: 'Stale', reason: 'Node runtime version changed' };
  }
  if (marker.inputSha256 !== dependencyInputHash(projectRoot, nodeVersion)) {
    return { status: 'Stale', reason: 'frontend dependency inputs changed' };
  }
  return { status: 'Current', reason: 'dependency inputs match the recorded install' };
}

function exitCodeForStatus(status) {
  if (status === 'Current') return CURRENT;
  if (status === 'Missing') return MISSING;
  if (status === 'Stale') return STALE;
  return EVALUATION_ERROR;
}

function runCli(args, projectRoot = path.resolve(__dirname, '..')) {
  const [command] = args;
  if (command === 'invalidate-build') invalidateBuild(projectRoot);
  else if (command === 'record-build') recordBuild(projectRoot);
  else if (command === 'build-state' || command === 'dependency-state') {
    const state = command === 'build-state'
      ? getBuildState(projectRoot)
      : getDependencyState(projectRoot);
    process.stdout.write(`${state.status}\n`);
    return exitCodeForStatus(state.status);
  } else if (command === 'invalidate-dependencies') invalidateDependencies(projectRoot);
  else if (command === 'record-dependencies') recordDependencies(projectRoot);
  else throw new Error(`Unknown frontend state command: ${command || '<missing>'}`);
  return CURRENT;
}

if (require.main === module) {
  try {
    process.exitCode = runCli(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = EVALUATION_ERROR;
  }
}

module.exports = {
  BUILD_SCHEMA_VERSION,
  DEPENDENCY_SCHEMA_VERSION,
  CURRENT,
  EVALUATION_ERROR,
  MISSING,
  STALE,
  buildInputHash,
  dependencyInputHash,
  getBuildState,
  getDependencyState,
  invalidateBuild,
  invalidateDependencies,
  recordBuild,
  recordDependencies,
  runCli,
};
