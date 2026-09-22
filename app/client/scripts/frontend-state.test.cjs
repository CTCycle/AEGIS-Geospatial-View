const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const {
  getBuildState,
  getDependencyState,
  invalidateBuild,
  recordBuild,
  recordDependencies,
} = require('./frontend-state.cjs');

function fixture() {
  const projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'aegis-frontend-state-'));
  const files = {
    'src/app.ts': 'export const value = 1;\n',
    'src/app/example.spec.ts': 'test-only 1\n',
    'src/app/e2e/example.ts': 'e2e-only 1\n',
    'src/test.ts': 'test bootstrap 1\n',
    'public/logo.txt': 'public asset 1\n',
    'angular.json': '{"projects":{}}\n',
    'package.json': '{"dependencies":{"runtime-lib":"1"},"scripts":{"build":"ng build"}}\n',
    'package-lock.json': '{"lockfileVersion":3,"packages":{}}\n',
    'tsconfig.json': '{"compilerOptions":{}}\n',
    'tsconfig.app.json': '{"compilerOptions":{}}\n',
    'tsconfig.spec.json': '{"compilerOptions":{"types":["jasmine"]}}\n',
    'karma.conf.cjs': 'module.exports = {};\n',
    'proxy.conf.cjs': 'module.exports = {};\n',
    '.nvmrc': '22.23.1\n',
    'node_modules/.package-lock.json': '{"lockfileVersion":3}\n',
  };
  for (const [relativePath, content] of Object.entries(files)) {
    const absolutePath = path.join(projectRoot, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, content, 'utf8');
  }
  fs.mkdirSync(path.join(projectRoot, 'dist', 'browser'), { recursive: true });
  fs.writeFileSync(path.join(projectRoot, 'dist', 'browser', 'index.html'), '<main>built</main>\n');
  fs.writeFileSync(path.join(projectRoot, 'dist', 'browser', 'main.js'), 'bundle 1\n');
  return projectRoot;
}

function clean(projectRoot) {
  fs.rmSync(projectRoot, { recursive: true, force: true });
}

function withFixture(callback) {
  const projectRoot = fixture();
  try {
    callback(projectRoot);
  } finally {
    clean(projectRoot);
  }
}

function makeBuildCurrent(projectRoot, nodeVersion = process.version) {
  recordBuild(projectRoot, nodeVersion);
  assert.equal(getBuildState(projectRoot, nodeVersion).status, 'Current');
}

test('same inputs and untouched output are current', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
  });
});

test('missing dist output is missing', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    fs.rmSync(path.join(projectRoot, 'dist', 'browser'), { recursive: true });
    assert.equal(getBuildState(projectRoot).status, 'Missing');
  });
});

test('missing build marker is missing', () => {
  withFixture((projectRoot) => {
    assert.equal(getBuildState(projectRoot).status, 'Missing');
  });
});

for (const relativePath of [
  'src/app.ts',
  'public/logo.txt',
  'angular.json',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  'tsconfig.app.json',
  '.nvmrc',
]) {
  test(`change to ${relativePath} makes the build stale`, () => {
    withFixture((projectRoot) => {
      makeBuildCurrent(projectRoot);
      fs.appendFileSync(path.join(projectRoot, relativePath), 'changed\n');
      assert.equal(getBuildState(projectRoot).status, 'Stale');
    });
  });
}

test('Node runtime version mismatch makes the build stale', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot, process.version);
    assert.equal(getBuildState(projectRoot, `${process.version}.other`).status, 'Stale');
  });
});

test('modified generated output makes the build stale', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    fs.appendFileSync(path.join(projectRoot, 'dist', 'browser', 'main.js'), 'changed\n');
    assert.equal(getBuildState(projectRoot).status, 'Stale');
  });
});

test('corrupt build marker is stale', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    fs.writeFileSync(path.join(projectRoot, 'dist', '.aegis-build-state.json'), '{bad json');
    assert.equal(getBuildState(projectRoot).status, 'Stale');
  });
});

test('test-only source changes do not invalidate a production build', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    fs.appendFileSync(path.join(projectRoot, 'src/app/example.spec.ts'), 'changed\n');
    fs.appendFileSync(path.join(projectRoot, 'src/app/e2e/example.ts'), 'changed\n');
    fs.appendFileSync(path.join(projectRoot, 'src/test.ts'), 'changed\n');
    assert.equal(getBuildState(projectRoot).status, 'Current');
  });
});

test('proxy, Karma, and test tsconfig changes do not invalidate a production build', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    for (const relativePath of ['proxy.conf.cjs', 'karma.conf.cjs', 'tsconfig.spec.json']) {
      fs.appendFileSync(path.join(projectRoot, relativePath), 'changed\n');
    }
    assert.equal(getBuildState(projectRoot).status, 'Current');
  });
});

test('failed or incomplete build cannot retain a current marker', () => {
  withFixture((projectRoot) => {
    makeBuildCurrent(projectRoot);
    invalidateBuild(projectRoot);
    fs.rmSync(path.join(projectRoot, 'dist', 'browser', 'index.html'));
    assert.throws(() => recordBuild(projectRoot), /entrypoint is missing/);
    assert.equal(getBuildState(projectRoot).status, 'Missing');
  });
});

test('dependency state is current after recording and ignores script-only changes', () => {
  withFixture((projectRoot) => {
    recordDependencies(projectRoot, process.version);
    assert.equal(getDependencyState(projectRoot, process.version).status, 'Current');
    const packagePath = path.join(projectRoot, 'package.json');
    const packageManifest = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
    packageManifest.scripts.test = 'ng test';
    fs.writeFileSync(packagePath, JSON.stringify(packageManifest));
    assert.equal(getDependencyState(projectRoot, process.version).status, 'Current');
  });
});

test('dependency fields, lock state, and Node version invalidate the install marker', () => {
  withFixture((projectRoot) => {
    recordDependencies(projectRoot, process.version);
    const packagePath = path.join(projectRoot, 'package.json');
    const packageManifest = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
    packageManifest.dependencies['runtime-lib'] = '2';
    fs.writeFileSync(packagePath, JSON.stringify(packageManifest));
    assert.equal(getDependencyState(projectRoot, process.version).status, 'Stale');
    assert.equal(getDependencyState(projectRoot, `${process.version}.other`).status, 'Stale');
    fs.writeFileSync(packagePath, JSON.stringify({ dependencies: { 'runtime-lib': '1' } }));
    fs.appendFileSync(path.join(projectRoot, 'node_modules/.package-lock.json'), 'changed');
    assert.equal(getDependencyState(projectRoot, process.version).status, 'Stale');
  });
});
