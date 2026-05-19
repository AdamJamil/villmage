import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";

const REPO_ROOT = "/home/tack/code/villmage";
const VIEWER_PATH = path.join(REPO_ROOT, "observability", "viewer.html");
const SORTED_GROUPED_FIXTURE = path.join(
  REPO_ROOT,
  "tests",
  "fixtures",
  "observability",
  "sorted_grouped",
);
const REPLAY_CORE_FIXTURE = path.join(
  REPO_ROOT,
  "tests",
  "fixtures",
  "observability",
  "replay_core",
);

/**
 * Return the JS API exported by the standalone viewer HTML.
 *
 * @param {(url: string) => Promise<{json: () => Promise<object>, text: () => Promise<string>}>} fetchImpl
 * @returns {Promise<{
 *   loadAllCheckpoints: (dataDir: string) => Promise<object[]>,
 *   loadDeltaIndex: (dataDir: string) => Promise<Map<number, object[]>>,
 *   reconstructStateAt: (checkpoints: object[], deltaIndex: Map<number, object[]>, targetTime: number) => {villager_states: Map<string, object>, world_state: object},
 * }>}
 */
async function loadViewerApi(fetchImpl) {
  const viewerHtml = await readFile(VIEWER_PATH, "utf8");
  const scriptMatch = viewerHtml.match(/<script>([\s\S]*)<\/script>/);
  assert.notEqual(scriptMatch, null, "viewer.html must expose one inline script.");
  const context = vm.createContext({
    globalThis: {},
    console,
    fetch: fetchImpl,
    JSON,
    Map,
    Set,
    URL,
  });
  vm.runInContext(scriptMatch[1], context);
  return context.globalThis.villmageObservability;
}

/**
 * Return an HTML directory listing with links in the requested order.
 *
 * @param {string[]} entries
 * @returns {string}
 */
function buildDirectoryListing(entries) {
  return `<!DOCTYPE html><html><body>${entries
    .map((entry) => `<a href="${entry}">${entry}</a>`)
    .join("")}</body></html>`;
}

/**
 * Return a fetch implementation backed by one fixture directory.
 *
 * @param {string} fixtureDir
 * @param {string[]} checkpointListing
 * @returns {{baseUrl: string, fetchImpl: (url: string) => Promise<{json: () => Promise<object>, text: () => Promise<string>}>}}
 */
function createFixtureFetch(fixtureDir, checkpointListing) {
  const baseUrl = "http://fixture.test";
  return {
    baseUrl,
    fetchImpl: async (url) => {
      const requestUrl = new URL(url, baseUrl);
      if (requestUrl.pathname === "/checkpoints/") {
        const listingHtml = buildDirectoryListing(checkpointListing);
        return {
          json: async () => JSON.parse(listingHtml),
          text: async () => listingHtml,
        };
      }

      const relativePath = requestUrl.pathname.replace(/^\//, "");
      const filePath = path.join(fixtureDir, relativePath);
      if (!existsSync(filePath)) {
        throw new Error(`Missing fixture file: ${filePath}`);
      }
      const fileText = await readFile(filePath, "utf8");
      return {
        json: async () => JSON.parse(fileText),
        text: async () => fileText,
      };
    },
  };
}

test("loadAllCheckpoints returns checkpoints sorted by game_time", async () => {
  const fixtureFetch = createFixtureFetch(SORTED_GROUPED_FIXTURE, [
    "00720.json",
    "00360.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  assert.equal(
    checkpoints.map((checkpoint) => checkpoint.game_time).join(","),
    "360,720",
  );
});

test("loadDeltaIndex groups records by game_time", async () => {
  const fixtureFetch = createFixtureFetch(SORTED_GROUPED_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  assert.equal(deltaIndex.get(400)?.length, 2);
  assert.equal(deltaIndex.get(600)?.length, 1);
});

test("reconstructStateAt returns the checkpoint baseline when no deltas exist", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, new Map(), 360);
  const aldric = reconstructed.villager_states.get("aldric");
  const sewalt = reconstructed.villager_states.get("sewalt");

  assert.equal(aldric.wakefulness, 100);
  assert.equal(aldric.satiation, 1500);
  assert.equal(aldric.inventory.PEACH, 1);
  assert.equal(sewalt.hydration, 4700);
  assert.equal(reconstructed.world_state.base_storage.PEACH, 2);
  assert.equal(reconstructed.world_state.water_supply_ml, 9000);
  assert.equal(reconstructed.world_state.fire_lit, false);
  assert.equal(reconstructed.world_state.total_dirtiness, 1);
});

test("reconstructStateAt applies VILLAGER_STATS deltas", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 400);

  assert.equal(reconstructed.villager_states.get("aldric").wakefulness, 85);
  assert.notEqual(reconstructed.villager_states.get("aldric").wakefulness, 100);
});

test("reconstructStateAt applies VILLAGER_INV deltas", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 420);

  assert.equal(reconstructed.villager_states.get("sewalt").inventory.PEACH, 3);
});

test("reconstructStateAt applies WORLD_STATE deltas", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 450);

  assert.equal(reconstructed.world_state.fire_lit, true);
});

test("reconstructStateAt applies MEMORY_UPDATE deltas", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 500);

  assert.ok(
    reconstructed.villager_states
      .get("aldric")
      .short_term_memory_texts.includes("Aldric remembers the flare-up."),
  );
});

test("reconstructStateAt starts from the nearest preceding checkpoint", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 600);

  assert.equal(reconstructed.world_state.base_storage.PEACH, 4);
  assert.equal(reconstructed.world_state.base_storage.FIREWOOD, 3);
});

test("reconstructStateAt isolates changed_fields to the exact target time", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 500);
  const changedFields = reconstructed.villager_states.get("aldric").changed_fields;

  assert.equal(changedFields.has("satiation"), true);
  assert.equal(changedFields.has("wakefulness"), false);
});

test("reconstructStateAt does not resurrect dead villagers", async () => {
  const fixtureFetch = createFixtureFetch(REPLAY_CORE_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewerApi = await loadViewerApi(fixtureFetch.fetchImpl);
  const checkpoints = await viewerApi.loadAllCheckpoints(fixtureFetch.baseUrl);
  const deltaIndex = await viewerApi.loadDeltaIndex(fixtureFetch.baseUrl);
  const reconstructed = viewerApi.reconstructStateAt(checkpoints, deltaIndex, 800);

  assert.equal(reconstructed.villager_states.has("aldric"), false);
});
