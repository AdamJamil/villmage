import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";

const REPO_ROOT = "/home/tack/code/villmage";
const VIEWER_PATH = path.join(REPO_ROOT, "observability", "viewer.html");
const VIEWER_UI_FIXTURE = path.join(
  REPO_ROOT,
  "tests",
  "fixtures",
  "observability",
  "viewer_ui",
);

/**
 * One minimal text node.
 */
class FakeTextNode {
  /**
   * @param {string} text
   */
  constructor(text) {
    this.parentNode = null;
    this.text = text;
  }

  /**
   * @returns {string}
   */
  get textContent() {
    return this.text;
  }

  /**
   * @param {string} value
   * @returns {void}
   */
  set textContent(value) {
    this.text = value;
  }
}

/**
 * One minimal class-list implementation.
 */
class FakeClassList {
  /**
   * @param {FakeElement} element
   */
  constructor(element) {
    this.element = element;
    this.values = new Set();
  }

  /**
   * @returns {void}
   */
  syncFromString() {
    this.values = new Set(
      this.element._className.split(/\s+/).filter((value) => value !== ""),
    );
  }

  /**
   * @returns {void}
   */
  syncToString() {
    this.element._className = [...this.values].join(" ");
  }

  /**
   * @param {...string} tokens
   * @returns {void}
   */
  add(...tokens) {
    for (const token of tokens) {
      this.values.add(token);
    }
    this.syncToString();
  }

  /**
   * @param {...string} tokens
   * @returns {void}
   */
  remove(...tokens) {
    for (const token of tokens) {
      this.values.delete(token);
    }
    this.syncToString();
  }

  /**
   * @param {string} token
   * @param {boolean} [force]
   * @returns {boolean}
   */
  toggle(token, force) {
    if (force === true) {
      this.values.add(token);
      this.syncToString();
      return true;
    }
    if (force === false) {
      this.values.delete(token);
      this.syncToString();
      return false;
    }
    if (this.values.has(token)) {
      this.values.delete(token);
      this.syncToString();
      return false;
    }
    this.values.add(token);
    this.syncToString();
    return true;
  }

  /**
   * @param {string} token
   * @returns {boolean}
   */
  contains(token) {
    return this.values.has(token);
  }
}

/**
 * One minimal element node with enough DOM for the viewer.
 */
class FakeElement extends EventTarget {
  /**
   * @param {FakeDocument} ownerDocument
   * @param {string} tagName
   */
  constructor(ownerDocument, tagName) {
    super();
    this.ownerDocument = ownerDocument;
    this.tagName = tagName.toUpperCase();
    this.parentNode = null;
    this.childNodes = [];
    this.attributes = new Map();
    this.dataset = new Proxy(
      {},
      {
        set: (_, property, value) => {
          const dataName = String(property)
            .replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
          this.attributes.set(`data-${dataName}`, String(value));
          this[`__data_${String(property)}`] = String(value);
          return true;
        },
        get: (_, property) => this[`__data_${String(property)}`],
      },
    );
    this._id = "";
    this._className = "";
    this.classList = new FakeClassList(this);
    this.scrollTop = 0;
    this.value = "";
    this.style = {};
  }

  /**
   * @returns {FakeElement[]}
   */
  get children() {
    return this.childNodes.filter((node) => node instanceof FakeElement);
  }

  /**
   * @returns {string}
   */
  get id() {
    return this._id;
  }

  /**
   * @param {string} value
   * @returns {void}
   */
  set id(value) {
    this._id = value;
    this.attributes.set("id", value);
    this.ownerDocument._registerId(this);
  }

  /**
   * @returns {string}
   */
  get className() {
    return this._className;
  }

  /**
   * @param {string} value
   * @returns {void}
   */
  set className(value) {
    this._className = value;
    this.attributes.set("class", value);
    this.classList.syncFromString();
  }

  /**
   * @returns {string}
   */
  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }

  /**
   * @param {string} value
   * @returns {void}
   */
  set textContent(value) {
    this.childNodes = [new FakeTextNode(value)];
  }

  /**
   * @returns {string}
   */
  get innerHTML() {
    return "";
  }

  /**
   * @param {string} html
   * @returns {void}
   */
  set innerHTML(html) {
    this.childNodes = parseHtmlFragment(this.ownerDocument, html);
    for (const childNode of this.childNodes) {
      childNode.parentNode = this;
    }
  }

  /**
   * @param {string} name
   * @param {string} value
   * @returns {void}
   */
  setAttribute(name, value) {
    this.attributes.set(name, value);
    if (name === "id") {
      this.id = value;
      return;
    }
    if (name === "class") {
      this.className = value;
      return;
    }
    if (name.startsWith("data-")) {
      const dataKey = name
        .slice(5)
        .split("-")
        .map((part, index) =>
          index === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1),
        )
        .join("");
      this[`__data_${dataKey}`] = value;
    }
  }

  /**
   * @param {FakeElement | FakeTextNode} child
   * @returns {FakeElement | FakeTextNode}
   */
  appendChild(child) {
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }

  /**
   * @param {string} selector
   * @returns {FakeElement | null}
   */
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  /**
   * @param {string} selector
   * @returns {FakeElement[]}
   */
  querySelectorAll(selector) {
    return querySelectorAllFrom(this, selector);
  }

  /**
   * @returns {{top: number, bottom: number}}
   */
  getBoundingClientRect() {
    if (this.dataset.eventIndex !== undefined && this.parentNode instanceof FakeElement) {
      const height = 96;
      const offsetTop = Number(this.dataset.eventIndex) * height;
      const top = offsetTop - this.parentNode.scrollTop;
      return { top, bottom: top + height };
    }
    return { top: 0, bottom: 600 };
  }

  /**
   * @returns {number}
   */
  get offsetTop() {
    if (this.dataset.eventIndex !== undefined) {
      return Number(this.dataset.eventIndex) * 96;
    }
    if (!(this.parentNode instanceof FakeElement)) {
      return 0;
    }
    return this.parentNode.children.indexOf(this) * 96;
  }

  /**
   * @returns {void}
   */
  click() {
    this.dispatchEvent(new Event("click", { bubbles: true }));
  }

  /**
   * @param {{block?: string}} [_options]
   * @returns {void}
   */
  scrollIntoView(_options) {
    if (this.parentNode instanceof FakeElement) {
      this.parentNode.scrollTop = this.offsetTop;
    }
  }
}

/**
 * One minimal document.
 */
class FakeDocument {
  constructor() {
    this._idMap = new Map();
    this.body = new FakeElement(this, "body");
  }

  /**
   * @param {string} tagName
   * @returns {FakeElement}
   */
  createElement(tagName) {
    return new FakeElement(this, tagName);
  }

  /**
   * @param {string} id
   * @returns {FakeElement | null}
   */
  getElementById(id) {
    return this._idMap.get(id) || null;
  }

  /**
   * @param {string} selector
   * @returns {FakeElement | null}
   */
  querySelector(selector) {
    return this.body.querySelector(selector);
  }

  /**
   * @param {string} selector
   * @returns {FakeElement[]}
   */
  querySelectorAll(selector) {
    return this.body.querySelectorAll(selector);
  }

  /**
   * @param {FakeElement} element
   * @returns {void}
   */
  _registerId(element) {
    if (element.id !== "") {
      this._idMap.set(element.id, element);
    }
  }
}

/**
 * Return all descendants of one element.
 *
 * @param {FakeElement} root
 * @returns {FakeElement[]}
 */
function descendants(root) {
  const found = [];
  for (const child of root.children) {
    found.push(child);
    found.push(...descendants(child));
  }
  return found;
}

/**
 * Return whether one element matches one simple selector.
 *
 * @param {FakeElement} element
 * @param {string} selector
 * @returns {boolean}
 */
function matchesSimpleSelector(element, selector) {
  if (selector.startsWith("#")) {
    return element.id === selector.slice(1);
  }
  if (selector.startsWith(".")) {
    return element.classList.contains(selector.slice(1));
  }
  const attributeMatch = selector.match(/^\[([^=\]]+)(?:="(.*)")?\]$/);
  if (attributeMatch !== null) {
    const attributeName = attributeMatch[1];
    const attributeValue = attributeMatch[2];
    const actualValue = element.attributes.get(attributeName) || null;
    if (attributeValue === undefined) {
      return actualValue !== null;
    }
    return actualValue === attributeValue.replace(/\\\./g, ".");
  }
  return element.tagName.toLowerCase() === selector.toLowerCase();
}

/**
 * Return matching descendants for one selector chain.
 *
 * @param {FakeElement} root
 * @param {string} selector
 * @returns {FakeElement[]}
 */
function querySelectorAllFrom(root, selector) {
  const parts = selector.trim().split(/\s+/);
  let current = [root];
  for (const part of parts) {
    const next = [];
    for (const base of current) {
      for (const candidate of descendants(base)) {
        if (matchesSimpleSelector(candidate, part)) {
          next.push(candidate);
        }
      }
    }
    current = next;
  }
  return current;
}

/**
 * Parse one narrow HTML fragment into fake nodes.
 *
 * @param {FakeDocument} document
 * @param {string} html
 * @returns {(FakeElement | FakeTextNode)[]}
 */
function parseHtmlFragment(document, html) {
  const root = new FakeElement(document, "fragment");
  const stack = [root];
  const tokenPattern = /<[^>]+>|[^<]+/g;
  for (const token of html.match(tokenPattern) || []) {
    if (token.startsWith("</")) {
      stack.pop();
      continue;
    }
    if (token.startsWith("<")) {
      const tagMatch = token.match(/^<([a-zA-Z0-9-]+)/);
      if (tagMatch === null) {
        continue;
      }
      const element = document.createElement(tagMatch[1]);
      const attributePattern = /([a-zA-Z0-9:-]+)="([^"]*)"/g;
      for (const attributeMatch of token.matchAll(attributePattern)) {
        element.setAttribute(attributeMatch[1], attributeMatch[2]);
      }
      stack[stack.length - 1].appendChild(element);
      if (!token.endsWith("/>")) {
        stack.push(element);
      }
      continue;
    }
    const trimmed = token.replace(/\s+/g, " ");
    if (trimmed.trim() === "") {
      continue;
    }
    stack[stack.length - 1].appendChild(new FakeTextNode(trimmed));
  }
  return root.childNodes;
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
        const listingHtml = `<!DOCTYPE html><html><body>${checkpointListing
          .map((entry) => `<a href="${entry}">${entry}</a>`)
          .join("")}</body></html>`;
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

/**
 * Return the exported viewer API with one fake DOM environment.
 *
 * @param {(url: string) => Promise<{json: () => Promise<object>, text: () => Promise<string>}>} fetchImpl
 * @returns {Promise<{api: Record<string, Function>, document: FakeDocument, root: FakeElement, flushTimers: () => Promise<void>}>}
 */
async function loadViewerUi(fetchImpl) {
  const viewerHtml = await readFile(VIEWER_PATH, "utf8");
  const scriptMatch = viewerHtml.match(/<script>([\s\S]*)<\/script>/);
  assert.notEqual(scriptMatch, null, "viewer.html must expose one inline script.");

  const document = new FakeDocument();
  const root = document.createElement("div");
  root.id = "viewer-root";
  document.body.appendChild(root);

  const context = vm.createContext({
    globalThis: {},
    console,
    fetch: fetchImpl,
    JSON,
    Map,
    Set,
    URL,
    URLSearchParams,
    encodeURIComponent,
    document,
    HTMLElement: FakeElement,
    Event,
    CSS: {
      escape(value) {
        return String(value).replace(/"/g, '\\"');
      },
    },
    location: { search: "" },
    requestAnimationFrame(callback) {
      callback(0);
      return 0;
    },
    setTimeout,
    clearTimeout,
    getComputedStyle(element) {
      return {
        backgroundColor:
          element === document.body ? "rgb(15, 20, 25)" : "rgba(0, 0, 0, 0)",
      };
    },
  });
  context.globalThis = context;
  vm.runInContext(scriptMatch[1], context);
  await Promise.resolve();
  return {
    api: context.globalThis.villmageObservability,
    document,
    root,
    flushTimers: async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

/**
 * Return all event texts currently rendered.
 *
 * @param {FakeDocument} document
 * @returns {string[]}
 */
function renderedEventTexts(document) {
  return document
    .querySelectorAll(".event-entry .event-text")
    .map((node) => node.textContent.trim());
}

/**
 * Return one stat value string.
 *
 * @param {FakeDocument} document
 * @param {string} statKey
 * @returns {string}
 */
function statValue(document, statKey) {
  const node = document.querySelector(`#stat-${statKey} .stat-value`);
  assert.notEqual(node, null, `Missing stat value for ${statKey}.`);
  return node.textContent.trim();
}

test("viewer UI renders, scrolls, highlights, and handles dead villagers", async () => {
  const fixtureFetch = createFixtureFetch(VIEWER_UI_FIXTURE, [
    "00360.json",
    "00720.json",
  ]);
  const viewer = await loadViewerUi(fixtureFetch.fetchImpl);
  const session = await viewer.api.mountViewer(fixtureFetch.baseUrl);
  await viewer.flushTimers();

  const bodyColor = "rgb(15, 20, 25)";
  const rgbValues = bodyColor.match(/\d+/g)?.slice(0, 3).map(Number) || [];
  assert.equal(rgbValues.every((value) => value < 60), true);

  const initialEvents = renderedEventTexts(viewer.document);
  assert.equal(initialEvents.length, 5);
  assert.equal(initialEvents[0], "Aldric checks the tents before sunrise.");
  assert.equal(initialEvents[4], "Aldric steadies himself and takes stock.");
  for (const timestampNode of viewer.document.querySelectorAll(".event-timestamp")) {
    assert.match(timestampNode.textContent.trim(), /^Day \d+, \d{1,2}:\d{2} (AM|PM)$/);
  }

  assert.equal(statValue(viewer.document, "wakefulness"), "35");
  assert.equal(statValue(viewer.document, "satiation"), "1280");
  assert.equal(statValue(viewer.document, "hydration"), "3800");
  assert.equal(statValue(viewer.document, "social_joy"), "79");
  assert.equal(statValue(viewer.document, "connectedness"), "64.0");
  assert.equal(statValue(viewer.document, "cleanliness"), "91");

  const relationshipCards = viewer.document.querySelectorAll("#relationship-list .relationship-card");
  assert.equal(relationshipCards.length, 2);
  assert.equal(
    relationshipCards.some((node) => node.textContent.includes("A reliable pair of hands.")),
    true,
  );
  assert.equal(
    relationshipCards.some((node) => node.textContent.includes("Brilliant, but fraying at the edges.")),
    true,
  );

  const eventLog = viewer.document.getElementById("event-log");
  const eventOne = viewer.document.getElementById("event-entry-1");
  assert.notEqual(eventLog, null);
  assert.notEqual(eventOne, null);
  eventLog.scrollTop = eventOne.offsetTop;
  eventLog.dispatchEvent(new Event("scroll"));
  await viewer.flushTimers();
  assert.equal(
    viewer.document.getElementById("stat-wakefulness")?.classList.contains("field-highlight"),
    true,
  );

  const eventTwo = viewer.document.getElementById("event-entry-2");
  assert.notEqual(eventTwo, null);
  eventLog.scrollTop = eventTwo.offsetTop;
  eventLog.dispatchEvent(new Event("scroll"));
  await viewer.flushTimers();
  assert.equal(
    viewer.document.getElementById("stat-wakefulness")?.classList.contains("field-highlight"),
    false,
  );
  assert.equal(
    viewer.document
      .getElementById("medium-term-memory-list")
      ?.textContent.includes("He keeps replaying the near miss."),
    true,
  );

  const eventThree = viewer.document.getElementById("event-entry-3");
  assert.notEqual(eventThree, null);
  eventLog.scrollTop = eventThree.offsetTop;
  eventLog.dispatchEvent(new Event("scroll"));
  await viewer.flushTimers();
  assert.equal(
    viewer.document.querySelector("#base-storage-PEACH .kv-value")?.textContent.trim(),
    "5",
  );
  assert.equal(
    viewer.document.getElementById("base-storage-PEACH")?.classList.contains("field-highlight"),
    true,
  );

  const eventFour = viewer.document.getElementById("event-entry-4");
  assert.notEqual(eventFour, null);
  eventLog.scrollTop = eventFour.offsetTop;
  eventLog.dispatchEvent(new Event("scroll"));
  await viewer.flushTimers();
  assert.equal(
    viewer.document.getElementById("base-storage-PEACH")?.classList.contains("field-highlight"),
    false,
  );

  const sewaltButton = viewer.document.querySelector('[data-villager-id="sewalt"]');
  assert.notEqual(sewaltButton, null);
  sewaltButton.click();
  await viewer.flushTimers();
  const sewaltEvents = renderedEventTexts(viewer.document);
  assert.equal(sewaltEvents.length, 3);
  assert.equal(sewaltEvents[0], "Sewalt wakes and checks the trail edge.");
  assert.equal(statValue(viewer.document, "wakefulness"), "22");
  assert.equal(statValue(viewer.document, "satiation"), "620");
  assert.equal(statValue(viewer.document, "hydration"), "1800");
  assert.equal(statValue(viewer.document, "social_joy"), "42");
  assert.equal(statValue(viewer.document, "connectedness"), "48.0");
  assert.equal(statValue(viewer.document, "cleanliness"), "44");

  const maelaButton = viewer.document.querySelector('[data-villager-id="maela"]');
  assert.notEqual(maelaButton, null);
  maelaButton.click();
  await viewer.flushTimers();
  assert.equal(
    viewer.document.getElementById("villager-life-state")?.textContent.trim(),
    "deceased",
  );
  assert.equal(statValue(viewer.document, "wakefulness"), "4");
  assert.equal(statValue(viewer.document, "hydration"), "600");
  assert.equal(
    viewer.document.getElementById("current-time-label")?.textContent.includes("10:10 AM"),
    true,
  );

  assert.equal(session.current_game_time, 610);
});
