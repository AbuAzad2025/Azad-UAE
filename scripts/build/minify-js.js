const fs = require("fs");
const path = require("path");
const { minify } = require("terser");

async function main() {
  const srcDir = path.resolve(__dirname, "../../static/js");
  const outDir = path.resolve(__dirname, "../../static/js/dist");
  
  fs.mkdirSync(outDir, { recursive: true });

  function getFiles(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "dist") continue;
        files.push(...getFiles(fullPath));
      } else if (entry.name.endsWith(".js") && !entry.name.endsWith(".min.js") && !entry.name.endsWith(".d.ts")) {
        files.push(fullPath);
      }
    }
    return files;
  }

  const files = getFiles(srcDir);
  console.log(`Found ${files.length} JS files to minify`);

  for (const file of files) {
    const relPath = path.relative(srcDir, file);
    const outPath = path.join(outDir, relPath);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });

    try {
      const code = fs.readFileSync(file, "utf8");
      const isModule = /\b(import|export)\b/.test(code);
      const result = await minify(code, {
        compress: {
          drop_console: false,
          pure_funcs: [],
        },
        mangle: { toplevel: false },
        module: isModule,
        output: {
          comments: false,
        },
      });
      fs.writeFileSync(outPath, result.code, "utf8");
      const saved = ((1 - result.code.length / code.length) * 100).toFixed(1);
      console.log(`  ${relPath}: ${code.length} -> ${result.code.length} bytes (${saved}% saved)`);
    } catch (err) {
      console.error(`  ${relPath}: ERROR - ${err.message}`);
    }
  }
  console.log(`\nOutput: ${path.relative(process.cwd(), outDir)}/`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});