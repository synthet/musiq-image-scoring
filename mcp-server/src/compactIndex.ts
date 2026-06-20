#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createBackendCompactMcpServer } from "./createBackendCompactMcpServer.js";
import { DISPATCH, SEARCH, SSE_STATUS, BE_MCP } from "./names.js";

async function main() {
    process.env.MCP_TOOL_PROFILE = "compact";
    const { server, toolDefs } = createBackendCompactMcpServer();
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error(`${BE_MCP} MCP v2.3.0 (${SEARCH}, ${DISPATCH}, ${SSE_STATUS})`);
    console.error(`Tools: ${toolDefs.map((t) => t.name).join(", ")}`);
}

main().catch((error) => {
    console.error("Fatal error running backend compact MCP:", error);
    process.exit(1);
});
