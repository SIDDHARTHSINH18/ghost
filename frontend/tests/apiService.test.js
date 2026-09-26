/**
 * Token-source consistency tests (frontend auth hardening).
 *
 * authService stores the session token in sessionStorage and is
 * the SINGLE token source. apiService must read it from there,
 * send it as `Authorization: Bearer <token>` on every
 * authenticated request, and must NOT keep its own localStorage
 * copy. A 401 still dispatches the `authExpired` event.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Browser globals the services expect (no jsdom needed).
class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
  clear() { this.map.clear(); }
}

const local = new MemoryStorage();
const session = new MemoryStorage();

globalThis.localStorage = local;
globalThis.sessionStorage = session;
globalThis.window = {
  dispatchEvent: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
};

const { default: apiService } = await import("../src/services/apiService");
const { default: authService } = await import("../src/services/authService");
const { default: graphService } = await import("../src/services/graphService");
import { AUTH_TOKEN_KEY } from "../src/utils/constants";

// fetch recorder
let lastRequest = null;
let nextResponse = () => new Response(JSON.stringify({ ok: true }), { status: 200 });

beforeEach(() => {
  local.clear();
  session.clear();
  globalThis.window.dispatchEvent.mockClear();
  lastRequest = null;
  nextResponse = () => new Response(JSON.stringify({ ok: true }), { status: 200 });

  globalThis.fetch = vi.fn(async (url, options = {}) => {
    lastRequest = { url, options };
    return nextResponse();
  });
});

describe("token storage ownership", () => {
  it("authService.setToken stores the token in sessionStorage", () => {
    authService.setToken("fresh-token-1");

    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("fresh-token-1");
    // the legacy localStorage copy must not exist
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });

  it("authService.getToken reads sessionStorage", () => {
    authService.setToken("fresh-token-2");

    expect(authService.getToken()).toBe("fresh-token-2");
  });

  it("authService.logout removes the token", () => {
    authService.setToken("to-be-removed");
    authService.logout();

    expect(authService.getToken()).toBeNull();
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });
});

describe("authenticated requests use the single token source", () => {
  it("authFetch sends Authorization: Bearer <fresh token>", async () => {
    authService.setToken("fresh-token-3");

    await apiService.authFetch("/api/graph");

    expect(lastRequest.options.headers.Authorization).toBe(
      "Bearer fresh-token-3"
    );
  });

  it("graph loading after login does NOT trigger authExpired", async () => {
    authService.setToken("fresh-token-4");

    nextResponse = () =>
      new Response(JSON.stringify({ success: true, nodes: [], edges: [] }), {
        status: 200,
      });

    await graphService.fetchGraphData();

    expect(globalThis.window.dispatchEvent).not.toHaveBeenCalled();
  });

  it("upload uses the same token source", async () => {
    authService.setToken("fresh-token-5");

    nextResponse = () => new Response(JSON.stringify({ id: "d1" }), { status: 200 });

    const fd = new FormData();
    fd.append("file", new Blob(["x"]), "a.txt");

    await apiService.upload(fd);

    expect(lastRequest.options.headers.Authorization).toBe(
      "Bearer fresh-token-5"
    );
  });

  it("a 401 dispatches authExpired (existing behavior preserved)", async () => {
    authService.setToken("expired-token");

    nextResponse = () =>
      new Response(JSON.stringify({ detail: "Authentication required." }), {
        status: 401,
      });

    const response = await apiService.authFetch("/api/graph");

    expect(response.status).toBe(401);
    expect(globalThis.window.dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "authExpired" })
    );
  });

  it("a missing token still signals authExpired on 401 without crashing", async () => {
    sessionStorage.clear();
    localStorage.clear();

    nextResponse = () =>
      new Response(JSON.stringify({ detail: "Authentication required." }), {
        status: 401,
      });

    const response = await apiService.authFetch("/api/graph");

    expect(response.status).toBe(401);
    expect(globalThis.window.dispatchEvent).toHaveBeenCalled();
  });
});
