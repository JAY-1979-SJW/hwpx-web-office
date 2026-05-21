#!/usr/bin/env node
/* viewer_core.renderPayloadToHTML 를 fixture JSON 으로 호출해
 * HTML 문자열을 stdout 으로 출력한다. RO-VIEW smoke 용.
 * 사용: node render_smoke.mjs <payload.json>
 */
import { readFileSync } from "node:fs";
import { renderPayloadToHTML } from "./viewer_core.mjs";

const path = process.argv[2];
if (!path) {
  console.error("usage: render_smoke.mjs <payload.json>");
  process.exit(2);
}
const payload = JSON.parse(readFileSync(path, "utf-8"));
const html = renderPayloadToHTML(payload);
process.stdout.write(html);
