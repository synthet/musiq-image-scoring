#!/usr/bin/env node
/**
 * Generate mcp/actions/playwright_registry.json from pinned Playwright MCP tool snapshots.
 * Source descriptors: mcp/actions/playwright_tools/*.json
 *
 * Re-run when upgrading @playwright/mcp (refresh snapshots first).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const TOOLS_DIR = path.join(ROOT, "mcp", "actions", "playwright_tools");
const OUT_PATH = path.join(ROOT, "mcp", "actions", "playwright_registry.json");

const EXTRA_TAGS = {
    browser_navigate: ["navigate", "url", "webui", "open page"],
    browser_snapshot: ["snapshot", "accessibility", "page state", "webui"],
    browser_click: ["click", "interact", "ui"],
    browser_take_screenshot: ["screenshot", "capture", "webui"],
    browser_type: ["type", "keyboard", "input"],
    browser_wait_for: ["wait", "selector", "load"],
};

const EXTRA_INTENTS = {
    browser_navigate: ["navigate to webui", "open localhost 7860", "browse scoring ui"],
    browser_snapshot: ["page snapshot", "accessibility tree", "what is on the page"],
    browser_click: ["click button on page", "click element in webui"],
    browser_take_screenshot: ["screenshot webui", "capture browser page"],
};

function toolNameToActionId(toolName) {
    if (!toolName.startsWith("browser_")) {
        throw new Error(`Expected browser_* tool name, got ${toolName}`);
    }
    const suffix = toolName.slice("browser_".length);
    return `browser.${suffix}`;
}

function humanTitle(toolName) {
    const suffix = toolName.replace(/^browser_/, "").replace(/_/g, " ");
    return suffix.replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildActionRecord(tool) {
    const toolName = tool.name;
    const actionId = toolNameToActionId(toolName);
    const isUnsafe = toolName === "browser_run_code_unsafe";

    const baseTags = ["browser", "playwright", "automation", "webui"];
    const tags = [...new Set([...baseTags, ...(EXTRA_TAGS[toolName] || [])])];

    const inputSchema = { ...(tool.arguments || { type: "object", properties: {} }) };
    if (inputSchema.additionalProperties === undefined) {
        inputSchema.additionalProperties = false;
    }

    return {
        action_id: actionId,
        title: humanTitle(toolName),
        description: tool.description || `Playwright MCP tool ${toolName}.`,
        category: "browser",
        tags,
        aliases: [toolName.replace(/_/g, " ")],
        intent_examples: EXTRA_INTENTS[toolName] || [
            `${toolName.replace(/^browser_/, "").replace(/_/g, " ")} in browser`,
        ],
        side_effect_level: isUnsafe ? "elevated" : "read_only",
        confirmation_required: isUnsafe,
        dry_run_supported: false,
        dispatch_enabled: true,
        review_required: isUnsafe,
        compact_profile_exposure: true,
        version: 1,
        deprecated: false,
        canonical_docs: ["docs/guides/setup/mcp-compact-servers.md"],
        api_contract_refs: [],
        auth_or_policy_requirements: [],
        input_schema: inputSchema,
        legacy_tool_name: toolName,
        handler_domain: "playwright",
    };
}

function main() {
    if (!fs.existsSync(TOOLS_DIR)) {
        console.error(`Missing tools directory: ${TOOLS_DIR}`);
        process.exit(1);
    }

    const files = fs
        .readdirSync(TOOLS_DIR)
        .filter((f) => f.endsWith(".json"))
        .sort();

    if (files.length === 0) {
        console.error(`No tool JSON files in ${TOOLS_DIR}`);
        process.exit(1);
    }

    const actions = [];
    for (const file of files) {
        const raw = JSON.parse(fs.readFileSync(path.join(TOOLS_DIR, file), "utf-8"));
        if (!raw.name) {
            console.error(`Tool descriptor missing name: ${file}`);
            process.exit(1);
        }
        actions.push(buildActionRecord(raw));
    }

    actions.sort((a, b) => a.action_id.localeCompare(b.action_id));

    const ids = actions.map((a) => a.action_id);
    if (new Set(ids).size !== ids.length) {
        console.error("Duplicate action_id in generated registry");
        process.exit(1);
    }

    const payload = {
        version: 1,
        repo: "backend-playwright",
        source: "mcp/actions/playwright_tools",
        categories: { browser: actions.length },
        actions,
    };

    fs.writeFileSync(OUT_PATH, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
    console.error(`Wrote ${actions.length} browser actions to ${OUT_PATH}`);
}

main();
