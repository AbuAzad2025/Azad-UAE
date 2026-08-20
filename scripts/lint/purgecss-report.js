/**
 * PurgeCSS analysis runner — uses the PurgeCSS JS API directly (the v8 CLI
 * has a Windows config-loading bug). Analysis-only: purged output and the
 * rejected-selector report go to the gitignored `coverage-frontend/purgecss/`.
 * Sources in `static/css/` are never modified.
 *
 * Run:  npm run css:purge
 */
const fs = require("fs");
const path = require("path");
const { PurgeCSS } = require("purgecss");

const config = require("../../purgecss.config.js");
const OUT_DIR = path.resolve(__dirname, "../../coverage-frontend/purgecss");

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const results = await new PurgeCSS().purge({ ...config, rejected: true });

  console.log("file,original,purged,kept%,rejected-selectors");
  for (const result of results) {
    const src = result.file;
    const original = fs.readFileSync(src, "utf8");
    const name = path.basename(src);
    fs.writeFileSync(path.join(OUT_DIR, name), result.css, "utf8");
    fs.writeFileSync(
      path.join(OUT_DIR, name.replace(/\.css$/, ".rejected.txt")),
      (result.rejected || []).join("\n") + "\n",
      "utf8",
    );
    const kept = ((result.css.length / original.length) * 100).toFixed(1);
    console.log(
      `${name},${original.length},${result.css.length},${kept}%,${(result.rejected || []).length}`,
    );
  }
  console.log(`\nOutput + rejected-selector reports: ${path.relative(process.cwd(), OUT_DIR)}/`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
