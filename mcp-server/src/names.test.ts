import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { BE_LIVE, BE_MCP, DISPATCH, SEARCH, SSE_STATUS } from "./names.js";

describe("backend MCP server names", () => {
    it("exports canonical is-be-* constants", () => {
        assert.equal(BE_MCP, "is-be-mcp");
        assert.equal(BE_LIVE, "is-be-live");
        assert.equal(SEARCH, "search");
        assert.equal(DISPATCH, "dispatch");
        assert.equal(SSE_STATUS, "sse_status");
    });
});
