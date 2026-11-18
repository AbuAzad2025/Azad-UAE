const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { minify } = require("terser");

function getFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "dist") continue;
      files.push(...getFiles(fullPath));
    } else if (
      entry.name.endsWith(".js") &&
      !entry.name.endsWith(".min.js") &&
      !entry.name.endsWith(".d.ts")
    ) {
      files.push(fullPath);
    }
  }
  return files;
}

// Cache-bust every relative module specifier, not just the top-level script.
// dist_url() hashes only js/dist/pos/index.js; a browser caches ./cart.js by
// its own URL, so a changed cart.js was never refetched after a deployment and
// the POS kept running the old totals code. Embedding the target's hash in the
// import makes its URL change whenever that target changes.
function hashOf(code) {
  return crypto.createHash("sha256").update(code, "utf8").digest("hex").slice(0, 12);
}

function addImportHashes(code, relPath, hashes) {
  return code.replace(/(["'])(\.{1,2}\/[^"']+\.js)\1/g, (match, quote, spec) => {
    const resolved = path.posix.normalize(
      path.posix.join(path.posix.dirname(relPath.split(path.sep).join("/")), spec),
    );
    const digest = hashes[resolved];
    return digest ? `${quote}${spec}?v=${digest}${quote}` : match;
  });
}

async function main() {
  const srcDir = path.resolve(__dirname, "../../static/js");
  const outDir = path.resolve(__dirname, "../../static/js/dist");

  fs.mkdirSync(outDir, { recursive: true });

  const files = getFiles(srcDir);
  console.log(`Found ${files.length} JS files to minify`);

  // Pass 1 — minify everything into memory so every target has a final body.
  const bundled = new Map();
  for (const file of files) {
    const relPath = path.relative(srcDir, file);
    try {
      const code = fs.readFileSync(file, "utf8");
      const isModule = /\b(import|export)\b/.test(code);
      const result = await minify(code, {
        compress: { drop_console: false, pure_funcs: [] },
        mangle: { toplevel: false },
        module: isModule,
        output: { comments: false },
      });
      bundled.set(relPath, { code: result.code, originalLength: code.length });
    } catch (err) {
      console.error(`  ${relPath}: ERROR - ${err.message}`);
    }
  }

  const hashes = {};
  for (const [rel, entry] of bundled) {
    hashes[rel.split(path.sep).join("/")] = hashOf(entry.code);
  }

  // Pass 2 — rewrite relative imports with the target's hash and write files.
  for (const [relPath, entry] of bundled) {
    const finalCode = addImportHashes(entry.code, relPath, hashes);
    const outPath = path.join(outDir, relPath);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, finalCode, "utf8");
    const saved = ((1 - finalCode.length / entry.originalLength) * 100).toFixed(1);
    console.log(
      `  ${relPath}: ${entry.originalLength} -> ${finalCode.length} bytes (${saved}% saved)`,
    );
  }
  console.log(`\nOutput: ${path.relative(process.cwd(), outDir)}/`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
