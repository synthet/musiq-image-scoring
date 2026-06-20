import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
    CallToolRequestSchema,
    ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { BE_MCP, DISPATCH, SEARCH, SSE_STATUS } from "./names.js";
import { dispatchWithPlaywrightProxy } from "./utils/proxyDispatch.js";
import { invokePythonTool } from "./utils/pythonBridge.js";

interface ToolDef {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
}

const compactToolDefs: ToolDef[] = [
    {
        name: SEARCH,
        description:
            "BM25 search over backend MCP actions; does not execute side effects.",
        inputSchema: {
            type: "object",
            properties: {
                query: { type: "string", description: "Natural language intent or keywords." },
                limit: { type: "number", description: "Max results (default 10)." },
                category: {
                    type: "string",
                    description: "Optional filter: diagnostics, jobs, data, browser, etc.",
                },
                side_effect_level: {
                    type: "string",
                    description: "Optional filter: read_only, write, elevated.",
                },
                read_only_only: {
                    type: "boolean",
                    description: "When true, omit mutating actions.",
                },
                pipeline_area: { type: "string" },
                include_schemas: {
                    type: "boolean",
                    description: "Include full input_schema on each result.",
                },
                include_docs: { type: "boolean" },
                include_elevated: { type: "boolean" },
            },
            required: ["query"],
        },
    },
    {
        name: DISPATCH,
        description: "Execute a backend action by action_id with schema validation.",
        inputSchema: {
            type: "object",
            properties: {
                action_id: {
                    type: "string",
                    description: "Registry action_id, e.g. diagnostics.get_error_summary.",
                },
                arguments: { type: "object", description: "Action arguments object." },
                dry_run: { type: "boolean" },
                confirmed: { type: "boolean" },
                request_id: { type: "string" },
                allow_deprecated: { type: "boolean" },
                expected_version: { type: "number" },
            },
            required: ["action_id"],
        },
    },
    {
        name: SSE_STATUS,
        description:
            "Read-only probe: whether is-be-live SSE is reachable (webui.lock or default 127.0.0.1:7860).",
        inputSchema: { type: "object", properties: {} },
    },
];

function toolResult(text: string, isError = false) {
    return {
        content: [{ type: "text" as const, text }],
        ...(isError ? { isError: true } : {}),
    };
}

async function handleCompactTool(name: string, args: Record<string, unknown>) {
    if (name === SEARCH) {
        const query = String(args.query ?? "").trim();
        if (!query) {
            return toolResult(JSON.stringify({ error: "query is required" }, null, 2), true);
        }
        const result = await invokePythonTool("search", args);
        return toolResult(JSON.stringify(result, null, 2));
    }

    if (name === DISPATCH) {
        const actionId = String(args.action_id ?? "").trim();
        if (!actionId) {
            return toolResult(JSON.stringify({ error: "action_id is required" }, null, 2), true);
        }
        const result = await dispatchWithPlaywrightProxy(
            actionId,
            (args.arguments ?? {}) as Record<string, unknown>,
            {
                dryRun: args.dry_run === true,
                confirmed: args.confirmed === true,
                requestId: args.request_id ? String(args.request_id) : undefined,
                allowDeprecated: args.allow_deprecated === true,
                expectedVersion: typeof args.expected_version === "number" ? args.expected_version : undefined,
            },
        );
        const isError = result.status === "error";
        return toolResult(JSON.stringify(result, null, 2), isError);
    }

    if (name === SSE_STATUS) {
        const result = await invokePythonTool("sse_status", {});
        return toolResult(JSON.stringify(result, null, 2));
    }

    throw new Error(`Unknown compact tool: ${name}`);
}

export function createBackendCompactMcpServer(): { server: Server; toolDefs: ToolDef[] } {
    const mcpServer = new Server({ name: BE_MCP, version: "2.3.0" }, { capabilities: { tools: {} } });

    mcpServer.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: compactToolDefs }));

    mcpServer.setRequestHandler(CallToolRequestSchema, async (request) => {
        const { name, arguments: toolArgs } = request.params;
        try {
            return await handleCompactTool(name, (toolArgs ?? {}) as Record<string, unknown>);
        } catch (error: unknown) {
            const msg = error instanceof Error ? error.message : String(error);
            return toolResult(`Error executing ${name}: ${msg}`, true);
        }
    });

    return { server: mcpServer, toolDefs: compactToolDefs };
}
