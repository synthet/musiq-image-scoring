import { invokePythonTool } from "./pythonBridge.js";
import {
    callPlaywrightTool,
    isPlaywrightEnabled,
    playwrightDisabledError,
    playwrightUnavailableError,
} from "./playwrightBridge.js";

export interface DispatchProxyOptions {
    dryRun?: boolean;
    confirmed?: boolean;
    requestId?: string;
    allowDeprecated?: boolean;
    expectedVersion?: number;
}

function isPlaywrightDelegate(result: Record<string, unknown>): boolean {
    return result.status === "proxy" && result.code === "playwright_delegate";
}

export { isPlaywrightDelegate };

function handlerErrorEnvelope(
    actionId: string,
    requestId: string | undefined,
    message: string,
    data: unknown,
): Record<string, unknown> {
    return {
        status: "error",
        code: "handler_error",
        message,
        action_id: actionId,
        request_id: requestId,
        details: { data },
    };
}

export async function dispatchWithPlaywrightProxy(
    actionId: string,
    args: Record<string, unknown> | null,
    opts: DispatchProxyOptions = {},
): Promise<Record<string, unknown>> {
    const requestId = opts.requestId;

    if (!isPlaywrightEnabled() && actionId.startsWith("browser.")) {
        return playwrightDisabledError(actionId, requestId);
    }

    const local = await invokePythonTool("dispatch", {
        action_id: actionId,
        arguments: args ?? {},
        dry_run: opts.dryRun === true,
        confirmed: opts.confirmed === true,
        request_id: requestId,
        allow_deprecated: opts.allowDeprecated === true,
        expected_version: opts.expectedVersion,
    });

    if (!isPlaywrightDelegate(local)) {
        return local;
    }

    if (opts.dryRun) {
        return local;
    }

    if (!isPlaywrightEnabled()) {
        return playwrightDisabledError(actionId, requestId);
    }

    const legacyTool = String(local.legacy_tool_name ?? "").trim();
    const validatedArgs = (local.validated_args ?? {}) as Record<string, unknown>;
    const rid = local.request_id ? String(local.request_id) : requestId;

    if (!legacyTool) {
        return handlerErrorEnvelope(actionId, rid, "Missing legacy_tool_name for Playwright delegate.", local);
    }

    try {
        const data = await callPlaywrightTool(legacyTool, validatedArgs);
        if (data && typeof data === "object" && !Array.isArray(data) && (data as { isError?: boolean }).isError) {
            const errPayload = (data as { error?: unknown }).error;
            const message =
                typeof errPayload === "object" && errPayload && "message" in errPayload
                    ? String((errPayload as { message: string }).message)
                    : "Playwright tool returned an error.";
            return handlerErrorEnvelope(actionId, rid, message, errPayload);
        }

        return {
            status: "success",
            action_id: actionId,
            action_version: local.action_version,
            request_id: rid,
            side_effect_level: local.side_effect_level ?? "read_only",
            dry_run: false,
            summary: `Playwright ${legacyTool} completed.`,
            data,
        };
    } catch (err) {
        return playwrightUnavailableError(
            actionId,
            rid,
            err instanceof Error ? err.message : String(err),
        );
    }
}
