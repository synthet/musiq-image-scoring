import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const DEFAULT_PACKAGE = "@playwright/mcp@latest";
const DEFAULT_CALL_TIMEOUT_MS = 120_000;

let client: Client | null = null;
let connectPromise: Promise<Client> | null = null;

export function isPlaywrightEnabled(): boolean {
    return process.env.MCP_PLAYWRIGHT_ENABLED?.trim() !== "0";
}

export function resolvePlaywrightPackage(): string {
    return process.env.MCP_PLAYWRIGHT_PACKAGE?.trim() || DEFAULT_PACKAGE;
}

function npxCommand(): string {
    return process.platform === "win32" ? "npx.cmd" : "npx";
}

function extractToolPayload(result: unknown): unknown {
    if (!result || typeof result !== "object") return result;
    const content = (result as { content?: Array<{ type: string; text?: string; data?: string; mimeType?: string }> }).content;
    const isError = (result as { isError?: boolean }).isError === true;
    if (!Array.isArray(content) || content.length === 0) {
        return result;
    }

    const parts = content.map((part) => {
        if (part.type === "text") {
            const text = part.text ?? "";
            const trimmed = text.trim();
            if (
                (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
                (trimmed.startsWith("[") && trimmed.endsWith("]"))
            ) {
                try {
                    return JSON.parse(trimmed);
                } catch {
                    return { text };
                }
            }
            return { text };
        }
        if (part.type === "image") {
            return {
                type: "image",
                mimeType: part.mimeType,
                data_length: (part.data ?? "").length,
            };
        }
        return part;
    });

    if (parts.length === 1) {
        return isError ? { error: parts[0], isError: true } : parts[0];
    }
    return isError ? { error: parts, isError: true } : parts;
}

async function ensureClient(): Promise<Client> {
    if (!isPlaywrightEnabled()) {
        throw new Error("Playwright integration disabled (MCP_PLAYWRIGHT_ENABLED=0)");
    }
    if (client) {
        return client;
    }
    if (connectPromise) {
        return connectPromise;
    }

    connectPromise = (async () => {
        const transport = new StdioClientTransport({
            command: npxCommand(),
            args: ["-y", resolvePlaywrightPackage()],
            env: process.env as Record<string, string>,
        });
        const nextClient = new Client({ name: "is-be-mcp-playwright", version: "2.3.0" });
        await nextClient.connect(transport);
        client = nextClient;
        return nextClient;
    })();

    try {
        return await connectPromise;
    } catch (err) {
        connectPromise = null;
        client = null;
        throw err;
    }
}

export function playwrightUnavailableError(
    actionId: string,
    requestId: string | undefined,
    error: string,
): Record<string, unknown> {
    return {
        status: "error",
        code: "playwright_unavailable",
        message:
            "Playwright MCP child is unavailable. Ensure Node.js 18+ and Playwright browsers are installed (npx playwright install).",
        action_id: actionId,
        request_id: requestId,
        details: { error },
    };
}

export function playwrightDisabledError(
    actionId: string,
    requestId: string | undefined,
): Record<string, unknown> {
    return {
        status: "error",
        code: "playwright_disabled",
        message: "Playwright browser actions are disabled (MCP_PLAYWRIGHT_ENABLED=0).",
        action_id: actionId,
        request_id: requestId,
    };
}

export async function callPlaywrightTool(
    toolName: string,
    args: Record<string, unknown>,
    timeoutMs = DEFAULT_CALL_TIMEOUT_MS,
): Promise<unknown> {
    const active = await ensureClient();
    const result = await Promise.race([
        active.callTool({ name: toolName, arguments: args }),
        new Promise<never>((_, reject) => {
            setTimeout(
                () => reject(new Error(`Playwright tool '${toolName}' timed out after ${timeoutMs}ms`)),
                timeoutMs,
            );
        }),
    ]);
    return extractToolPayload(result);
}

export async function shutdownPlaywrightClient(): Promise<void> {
    if (client) {
        await client.close().catch(() => undefined);
        client = null;
    }
    connectPromise = null;
}

process.on("exit", () => {
    void shutdownPlaywrightClient();
});
