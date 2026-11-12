// Copies the on-device card reader (tesseract.js) into public/ocr so it is served
// from our own site: nothing is fetched from other sites, and the card photo
// never leaves the person's device (Cooper, 2026-11-12). Runs before each build.
import { cpSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const out = join(process.cwd(), "public", "ocr");
mkdirSync(join(out, "lang"), { recursive: true });
const tjs = dirname(require.resolve("tesseract.js/package.json"));
cpSync(join(tjs, "dist", "worker.min.js"), join(out, "worker.min.js"));
const core = dirname(require.resolve("tesseract.js-core/package.json"));
for (const f of readdirSync(core)) {
  if (/^tesseract-core.*lstm\.wasm\.js$/.test(f)) cpSync(join(core, f), join(out, f));
}
const eng = dirname(require.resolve("@tesseract.js-data/eng/package.json"));
cpSync(join(eng, "4.0.0_best_int", "eng.traineddata.gz"), join(out, "lang", "eng.traineddata.gz"));
console.log("on-device card reader copied to public/ocr");
