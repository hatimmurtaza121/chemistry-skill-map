#!/usr/bin/env node
/**
 * validate.mjs — integrity check for skill graph datasets.
 */

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DATA = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'data');
const load = (path) => JSON.parse(readFileSync(resolve(DATA, path), 'utf8'));
const bytesOf = (path) => readFileSync(resolve(DATA, path));

const errors = [];
const check = (cond, msg) => { if (!cond) errors.push(msg); };

function validateMap(map) {
  const prefix = `maps/${map.id}`;
  const topics = load(`${prefix}/topics.json`);
  const deps = load(`${prefix}/dependencies.json`);
  const standards = load(`${prefix}/curriculum-standards.json`);
  const manifest = load(`${prefix}/manifest.json`);

  check(topics.topicCount === topics.topics.length,
    `${map.id}: topicCount ${topics.topicCount} != ${topics.topics.length}`);
  check(deps.edgeCount === deps.dependencies.length,
    `${map.id}: edgeCount ${deps.edgeCount} != ${deps.dependencies.length}`);

  const topicIds = new Set();
  for (const t of topics.topics) {
    check(typeof t.id === 'string' && (t.id.startsWith('ms_') || t.id.startsWith('chem_')), `${map.id}: bad id ${t.id}`);
    check(typeof t.name === 'string' && t.name.length > 0, `${map.id}: empty name ${t.id}`);
    if (topicIds.has(t.id)) errors.push(`${map.id}: duplicate topic id ${t.id}`);
    topicIds.add(t.id);
  }

  const standardKeys = new Set();
  for (const c of standards.curricula) {
    for (const s of c.topics) {
      if (standardKeys.has(s.key)) errors.push(`${map.id}: duplicate standard ${s.key}`);
      standardKeys.add(s.key);
    }
  }

  for (const d of deps.dependencies) {
    check(topicIds.has(d.topicId), `${map.id}: unknown topicId ${d.topicId}`);
    check(topicIds.has(d.prerequisiteId), `${map.id}: unknown prerequisiteId ${d.prerequisiteId}`);
    check(d.topicId !== d.prerequisiteId, `${map.id}: self-dependency ${d.topicId}`);
    check(d.strength === 'hard' || d.strength === 'soft', `${map.id}: bad strength ${d.strength}`);
  }

  const adj = new Map([...topicIds].map((id) => [id, []]));
  for (const d of deps.dependencies) adj.get(d.topicId).push(d.prerequisiteId);

  const visiting = new Set();
  const visited = new Set();
  function hasCycle(node) {
    if (visiting.has(node)) return true;
    if (visited.has(node)) return false;
    visiting.add(node);
    for (const nxt of adj.get(node) ?? []) {
      if (hasCycle(nxt)) return true;
    }
    visiting.delete(node);
    visited.add(node);
    return false;
  }
  for (const id of topicIds) {
    if (hasCycle(id)) {
      errors.push(`${map.id}: dependency graph contains a cycle`);
      break;
    }
  }

  for (const [name, meta] of Object.entries(manifest.files ?? {})) {
    const actual = createHash('sha256').update(bytesOf(`${prefix}/${name}`)).digest('hex');
    check(actual === meta.sha256, `${map.id}: checksum mismatch for ${name}`);
  }

  return { topics, deps, standardKeys };
}

const catalog = load('maps.json');
check(catalog.maps?.length > 0, 'maps.json has no maps');
check(catalog.maps.some(m => m.id === catalog.defaultMap), 'defaultMap not found in catalog');

let summary = [];
for (const map of catalog.maps.filter(m => m.available)) {
  const { topics, deps, standardKeys } = validateMap(map);
  summary.push(`${map.name}: ${topics.topics.length} skills, ${deps.dependencies.length} edges`);
}

if (errors.length) {
  console.error(`✗ ${errors.length} problem(s):`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}
console.log(`✓ valid — ${summary.join('; ')} (${summary.length} map(s)).`);
