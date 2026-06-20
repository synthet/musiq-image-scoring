import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isPlaywrightDelegate } from "./proxyDispatch.js";

describe("backend proxyDispatch", () => {
    it("isPlaywrightDelegate for playwright_delegate", () => {
        assert.equal(
            isPlaywrightDelegate({
                status: "proxy",
                code: "playwright_delegate",
                action_id: "browser.click",
            }),
            true,
        );
    });

    it("isPlaywrightDelegate false for python success", () => {
        assert.equal(
            isPlaywrightDelegate({
                status: "success",
                action_id: "diagnostics.get_error_summary",
            }),
            false,
        );
    });
});
