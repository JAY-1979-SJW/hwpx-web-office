#!/usr/bin/env node
/* WEB-OFFICE-BROWSER-RUNTIME-SMOKE-01
 * payload.sample.json 을 viewer_core 로 렌더하고 HTML 을 stdout 으로 출력.
 * 편집/save/apply 토큰이 결과에 등장하지 않는다.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { renderPayloadToHTML } from "./viewer_core.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const payloadPath = process.argv[2]
  || resolve(here, "payload.sample.json");
const payload = JSON.parse(readFileSync(payloadPath, "utf-8"));
if (payload.editable !== false) {
  console.error("payload.editable must be false (RO-VIEW)");
  process.exit(2);
}
const html = renderPayloadToHTML(payload, { title: payload.documentId });
process.stdout.write(html);
