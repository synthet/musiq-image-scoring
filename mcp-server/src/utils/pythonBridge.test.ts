import assert from "node:assert/strict";
import { describe, it } from "node:test";

/**
 * Unit tests for request-id response routing (logic mirrored from pythonBridge).
 * Full worker I/O is covered by MCP protocol smoke tests.
 */

function stripRequestId(payload: Record<string, unknown>): Record<string, unknown> {
    if (!("_request_id" in payload)) {
        return payload;
    }
    const { _request_id: _ignored, ...rest } = payload;
    return rest;
}

describe("pythonBridge response routing", () => {
    it("stripRequestId removes _request_id", () => {
        const out = stripRequestId({
            _request_id: "abc",
            ok: true,
            server: "is-be-live",
        });
        assert.deepEqual(out, { ok: true, server: "is-be-live" });
        assert.equal("_request_id" in out, false);
    });

    it("stripRequestId passes through payloads without id", () => {
        const out = stripRequestId({ status: "success" });
        assert.deepEqual(out, { status: "success" });
    });
});
