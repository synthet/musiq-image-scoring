import { randomUUID } from "node:crypto";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = path.resolve(__dirname, "..", "..", "..");

const WORKER_SCRIPT = path.join(PROJECT_ROOT, "scripts", "mcp", "compact_worker.py");
const DEFAULT_VENV = "~/.venvs/tf/bin/activate";

interface PendingRequest {
    tool: string;
    resolve: (value: Record<string, unknown>) => void;
    reject: (reason: Error) => void;
    timer: ReturnType<typeof setTimeout>;
}

let worker: ChildProcessWithoutNullStreams | null = null;
const pendingById = new Map<string, PendingRequest>();
let buffer = "";
let writeChain: Promise<void> = Promise.resolve();

function windowsPathToWsl(winPath: string): string {
    const normalized = path.resolve(winPath).replace(/\\/g, "/");
    const match = /^([A-Za-z]):\/(.*)$/.exec(normalized);
    if (!match) return normalized;
    const drive = match[1].toLowerCase();
    return `/mnt/${drive}/${match[2]}`;
}

function shouldUseWsl(): boolean {
    const flag = process.env.IS_BE_MCP_USE_WSL?.trim();
    if (flag === "1") return true;
    if (flag === "0") return false;
    return process.platform === "win32";
}

function workerShellCommand(): { command: string; args: string[] } {
    const custom = process.env.IS_BE_MCP_WORKER_SHELL?.trim();
    if (custom) {
        return { command: "bash", args: ["-lc", custom] };
    }

    const venvActivate = process.env.IS_BE_MCP_VENV_ACTIVATE?.trim() || DEFAULT_VENV;
    const wslRoot = shouldUseWsl() ? windowsPathToWsl(PROJECT_ROOT) : PROJECT_ROOT;
    const workerPath = shouldUseWsl()
        ? `${wslRoot}/scripts/mcp/compact_worker.py`
        : WORKER_SCRIPT;

    const inner = `cd '${wslRoot.replace(/'/g, `'\\''`)}' && export ENABLE_MCP_SERVER=1 && export MCP_TOOL_PROFILE=compact && source ${venvActivate} && python '${workerPath.replace(/'/g, `'\\''`)}'`;

    if (shouldUseWsl()) {
        return { command: "wsl", args: ["bash", "-lc", inner] };
    }
    return { command: "bash", args: ["-lc", inner] };
}

function stripRequestId(payload: Record<string, unknown>): Record<string, unknown> {
    if (!("_request_id" in payload)) {
        return payload;
    }
    const { _request_id: _ignored, ...rest } = payload;
    return rest;
}

function rejectAllPending(error: Error): void {
    for (const entry of pendingById.values()) {
        clearTimeout(entry.timer);
        entry.reject(error);
    }
    pendingById.clear();
}

function resolvePending(id: string, payload: Record<string, unknown>): void {
    const entry = pendingById.get(id);
    if (!entry) {
        return;
    }
    pendingById.delete(id);
    clearTimeout(entry.timer);
    entry.resolve(stripRequestId(payload));
}

function rejectPending(id: string, error: Error): void {
    const entry = pendingById.get(id);
    if (!entry) {
        return;
    }
    pendingById.delete(id);
    clearTimeout(entry.timer);
    entry.reject(error);
}

function flushBuffer(): void {
    while (true) {
        const newline = buffer.indexOf("\n");
        if (newline < 0) {
            break;
        }
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) {
            continue;
        }

        let parsed: Record<string, unknown>;
        try {
            parsed = JSON.parse(line) as Record<string, unknown>;
        } catch (err) {
            rejectAllPending(err instanceof Error ? err : new Error(String(err)));
            return;
        }

        const reqId = parsed._request_id;
        if (typeof reqId !== "string" || !reqId) {
            rejectAllPending(new Error("Python worker response missing _request_id"));
            return;
        }
        resolvePending(reqId, parsed);
    }
}

function enqueueWrite(proc: ChildProcessWithoutNullStreams, payload: string): Promise<void> {
    writeChain = writeChain.then(
        () =>
            new Promise<void>((resolve, reject) => {
                proc.stdin.write(payload, (err) => {
                    if (err) {
                        reject(err);
                    } else {
                        resolve();
                    }
                });
            }),
    );
    return writeChain;
}

function ensureWorker(): ChildProcessWithoutNullStreams {
    if (worker && !worker.killed) {
        return worker;
    }

    if (!fs.existsSync(WORKER_SCRIPT)) {
        throw new Error(`Python worker not found: ${WORKER_SCRIPT}`);
    }

    buffer = "";
    writeChain = Promise.resolve();

    const { command, args } = workerShellCommand();
    worker = spawn(command, args, {
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
    });

    worker.stdout.setEncoding("utf8");
    worker.stdout.on("data", (chunk: string) => {
        buffer += chunk;
        flushBuffer();
    });

    worker.stderr.on("data", (chunk: Buffer | string) => {
        process.stderr.write(String(chunk));
    });

    worker.on("error", (err) => {
        rejectAllPending(err);
        worker = null;
    });

    worker.on("exit", (code, signal) => {
        worker = null;
        rejectAllPending(
            new Error(`Python compact worker exited (code=${code ?? "null"}, signal=${signal ?? "null"})`),
        );
    });

    return worker;
}

export async function invokePythonTool(
    tool: string,
    args: Record<string, unknown> = {},
    timeoutMs = 120_000,
): Promise<Record<string, unknown>> {
    const proc = ensureWorker();
    const id = randomUUID();

    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            rejectPending(id, new Error(`Python compact tool '${tool}' timed out after ${timeoutMs}ms`));
        }, timeoutMs);

        pendingById.set(id, { tool, resolve, reject, timer });

        const payload = JSON.stringify({ id, tool, args }) + "\n";
        enqueueWrite(proc, payload).catch((err) => {
            rejectPending(id, err instanceof Error ? err : new Error(String(err)));
        });
    });
}

export function shutdownPythonWorker(): void {
    if (worker && !worker.killed) {
        try {
            void enqueueWrite(worker, "__shutdown__\n");
        } catch {
            worker.kill();
        }
        worker = null;
    }
    rejectAllPending(new Error("Python compact worker shut down"));
}

process.on("exit", () => shutdownPythonWorker());

/** Test helper: number of in-flight + queued MCP→Python requests. */
export function pendingPythonRequestCount(): number {
    return pendingById.size;
}
