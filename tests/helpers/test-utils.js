const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const repoRoot = path.resolve(__dirname, '..', '..');

function repoPath(...segments) {
  return path.join(repoRoot, ...segments);
}

function readRepoFile(relativePath) {
  return fs.readFileSync(repoPath(relativePath), 'utf-8');
}

function createTempDir(prefix = '24h-testers-tests-') {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function writeTempFile(contents, filename = 'temp.md') {
  const dir = createTempDir();
  const filePath = path.join(dir, filename);
  fs.writeFileSync(filePath, contents, 'utf-8');
  return { dir, filePath };
}

module.exports = {
  repoRoot,
  repoPath,
  readRepoFile,
  createTempDir,
  writeTempFile,
};
