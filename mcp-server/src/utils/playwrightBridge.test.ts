import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
    isPlaywrightEnabled,
    playwrightDisabledError,
    playwrightUnavailableError,
    resolvePlaywrightPackage,
} from "./playwrightBridge.js";
import { isPlaywrightDelegate } from "./proxyDispatch.js";

describe("playwrightBridge helpers", () => {
    it("isPlaywrightEnabled defaults true", () => {
        delete process.env.MCP_PLAYWRIGHT_ENABLED;
        assert.equal(isPlaywrightEnabled(), true);
    });

    it("isPlaywrightEnabled respects MCP_PLAYWRIGHT_ENABLED=0", () => {
        process.env.MCP_PLAYWRIGHT_ENABLED = "0";
        try {
            assert.equal(isPlaywrightEnabled(), false);
        } finally {
            delete process.env.MCP_PLAYWRIGHT_ENABLED;
        }
    });

    it("resolvePlaywrightPackage defaults to @playwright/mcp@latest", () => {
        delete process.env.MCP_PLAYWRIGHT_PACKAGE;
        assert.equal(resolvePlaywrightPackage(), "@playwright/mcp@latest");
    });

    it("playwrightUnavailableError shape", () => {
        const err = playwrightUnavailableError("browser.navigate", "req-1", "spawn failed");
        assert.equal(err.status, "error");
        assert.equal(err.code, "playwright_unavailable");
        assert.equal(err.action_id, "browser.navigate");
        assert.equal(err.request_id, "req-1");
    });

    it("playwrightDisabledError shape", () => {
        const err = playwrightDisabledError("browser.snapshot", "req-2");
        assert.equal(err.code, "playwright_disabled");
    });
});

describe("backend MCP playwright proxy routing", () => {
    it("isPlaywrightDelegate detects delegate envelope", () => {
        assert.equal(
            isPlaywrightDelegate({
                status: "proxy",
                code: "playwright_delegate",
                legacy_tool_name: "browser_navigate",
            }),
            true,
        );
        assert.equal(isPlaywrightDelegate({ status: "success" }), false);
        assert.equal(
            isPlaywrightDelegate({ status: "error", code: "unknown_action" }),
            false,
        );
    });
});
