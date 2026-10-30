/**
 * Distribution of WebSocket connections between gateways (D5.7, D5.4).
 *
 * Opens N connections on behalf of several users and shows how many landed on each gateway.
 * With --watch the connections are kept and reopened, so you can restart a gateway meanwhile
 * and watch the distribution recover (printed every 2 s).
 *
 * Run from the project root (Node.js 22+, no dependencies):
 *
 *   node tools/ws-fleet.mjs --tokens tokens.txt --connections 20 --watch 60
 *   docker compose restart gateway-b     # in another terminal
 *   node tools/ws-fleet.mjs --tokens tokens.txt --connections 100           # D5.4
 *
 * tokens.txt: one access token per line (log in a few users first).
 * Environment: API (http://localhost:8080), ORIGIN (http://localhost:8081),
 *              TICKET_PATH (/v1/ws-tickets), WS_PATH (/v1/ws), HELLO_FIELD (gateway).
 *
 * What the tool expects from your system (compatibility, not extra lab requirements):
 *   - POST {API}{TICKET_PATH} with "Authorization: Bearer <token>" returns {"ticket": "..."};
 *   - the socket is {WS}{WS_PATH}?ticket=<ticket>;
 *   - the first frame of the gateway is JSON with its name in HELLO_FIELD,
 *     e.g. {"type": "hello", "gateway": "gateway-a"}.
 * Exit code 1 if some connections are not established at the end.
 */
import {readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";

const PRINT_EVERY_MS = 2000;
const NOT_CONNECTED = "not_connected";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * @typedef {object} Options
 * @property {string[]} tokens access tokens, used in turn by the connections
 * @property {number} [connections] how many connections to keep
 * @property {number} [watchSeconds] keep and reopen connections this long; 0 = connect once
 * @property {number} [timeoutMs] limit of one ticket request and of the gateway greeting
 * @property {string} [api] base URL of the API (behind the balancer)
 * @property {string} [origin] Origin header of the WebSocket handshake
 * @property {string} [ticketPath] route that issues tickets
 * @property {string} [wsPath] route of the WebSocket
 * @property {string} [field] field of the greeting frame with the gateway name
 * @property {number} [retryMs] pause before reopening a connection
 * @property {typeof fetch} [fetchImpl] replaceable in tests
 * @property {typeof WebSocket} [Socket] replaceable in tests
 * @property {(...args: unknown[]) => void} [log]
 * @property {(message: string) => void} [warn]
 */

/** @typedef {{ gateway: string | null, socket: WebSocket | null }} Entry */

/** Ask the system for a one-time WebSocket ticket. */
async function requestTicket(options, token, signal) {
    const response = await options.fetchImpl(options.api + options.ticketPath, {
        method: "POST",
        headers: {Authorization: `Bearer ${token}`},
        signal,
    });
    if (!response.ok) {
        throw new Error(`ticket HTTP ${response.status}`);
    }

    const body = await response.json();
    if (typeof body.ticket !== "string" || !body.ticket) {
        throw new Error("ticket response has no ticket");
    }
    return body.ticket;
}

/**
 * Open a socket and wait until it closes (or the run stops). The gateway name from the first
 * frame is written to the entry; a missing greeting or a socket error rejects.
 */
function holdConnection(entry, ticket, options, stopSignal) {
    const url = new URL(options.wsPath, options.api.replace(/^http/, "ws"));
    url.searchParams.set("ticket", ticket);

    const socket = new options.Socket(url.href, {headers: {Origin: options.origin}});
    entry.socket = socket;

    return new Promise((resolve, reject) => {
        const greetingTimer = setTimeout(
            () => reject(new Error("gateway greeting timed out")),
            options.timeoutMs,
        );

        const finish = () => {
            clearTimeout(greetingTimer);
            stopSignal.removeEventListener("abort", finish);
            resolve();
        };
        stopSignal.addEventListener("abort", finish, {once: true});

        socket.onmessage = (event) => {
            const name = gatewayName(event.data, options.field);
            if (name) {
                entry.gateway = name;
                clearTimeout(greetingTimer);
            }
        };

        socket.onerror = () => {
            clearTimeout(greetingTimer);
            reject(new Error("WebSocket connection failed"));
        };
        socket.onclose = finish;
    });
}

/** The gateway name from a frame, or null if the frame is not the greeting. */
function gatewayName(data, field) {
    try {
        const frame = JSON.parse(data);
        return typeof frame[field] === "string" && frame[field] ? frame[field] : null;
    } catch {
        return null; // not JSON: an ordinary message of the system, not the greeting
    }
}

/** Forget the entry's socket so its late events cannot change the counts. */
function release(entry) {
    entry.gateway = null;
    if (!entry.socket) {
        return;
    }

    entry.socket.onmessage = entry.socket.onerror = entry.socket.onclose = null;
    entry.socket.close();
    entry.socket = null;
}

function validate({tokens, connections, watchSeconds, timeoutMs}) {
    if (!tokens.length || tokens.some((token) => !token.trim())) {
        throw new Error("tokens must not be empty");
    }
    if (!Number.isSafeInteger(connections) || connections < 1) {
        throw new Error("connections must be a positive integer");
    }
    if (!Number.isFinite(watchSeconds) || watchSeconds < 0) {
        throw new Error("watch must be nonnegative");
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
        throw new Error("timeout must be positive");
    }
}

/** @param {Entry[]} entries */
function distribution(entries) {
    const counts = {};
    for (const {gateway} of entries) {
        const name = gateway ?? NOT_CONNECTED;
        counts[name] = (counts[name] ?? 0) + 1;
    }
    return counts;
}

/**
 * Observe the distribution of connections between gateways.
 * @param {Options} input
 * @returns {Promise<0 | 1>} 1 if some connections are not established at the end
 */
export async function observe(input) {
    const options = {
        connections: 20,
        watchSeconds: 0,
        timeoutMs: 10_000,
        api: "http://localhost:8080",
        origin: "http://localhost:8081",
        ticketPath: "/v1/ws-tickets",
        wsPath: "/v1/ws",
        field: "gateway",
        retryMs: 500,
        fetchImpl: fetch,
        Socket: WebSocket,
        log: console.log,
        warn: console.error,
        ...input,
    };

    validate(options);

    /** @type {Entry[]} */
    const entries = Array.from({length: options.connections}, () => ({gateway: null, socket: null}));
    const end = Date.now() + (options.watchSeconds ? options.watchSeconds * 1000 : options.timeoutMs);
    const stop = new AbortController();
    let failures = 0;

    async function maintain(entry, index) {
        while (!stop.signal.aborted && Date.now() < end) {
            try {
                const limit = AbortSignal.timeout(
                    Math.ceil(Math.max(1, Math.min(options.timeoutMs, end - Date.now()))),
                );
                const token = options.tokens[index % options.tokens.length];
                const ticket = await requestTicket(options, token, AbortSignal.any([stop.signal, limit]));
                if (stop.signal.aborted) {
                    break;
                }

                await holdConnection(entry, ticket, options, stop.signal);
            } catch (error) {
                if (!stop.signal.aborted) {
                    failures += 1;
                    options.warn(`connection ${index + 1}: ${error.message}`);
                }
            } finally {
                release(entry);
            }

            if (!stop.signal.aborted) {
                await sleep(Math.max(0, Math.min(options.retryMs, end - Date.now())));
            }
        }
    }

    const workers = entries.map(maintain);

    let nextPrint = Date.now();
    while (Date.now() < end) {
        if (!options.watchSeconds && entries.every((entry) => entry.gateway)) {
            break;
        }
        if (Date.now() >= nextPrint) {
            options.log(distribution(entries));
            nextPrint = Date.now() + PRINT_EVERY_MS;
        }
        await sleep(Math.max(1, Math.min(50, end - Date.now())));
    }

    const counts = distribution(entries);
    const missing = counts[NOT_CONNECTED] ?? 0;

    stop.abort();
    await Promise.all(workers);

    options.log("final:", counts, `errors: ${failures}; not connected: ${missing}`);
    return missing ? 1 : 0;
}

const USAGE = "usage: --tokens FILE --connections N [--watch SECONDS] [--timeout SECONDS]";
const FLAGS = new Set(["--tokens", "--connections", "--watch", "--timeout"]);

function parseArgs(argv) {
    const values = new Map();
    for (let i = 0; i < argv.length; i += 2) {
        const [flag, value] = [argv[i], argv[i + 1]];
        if (!FLAGS.has(flag) || !value || value.startsWith("--")) {
            throw new Error(USAGE);
        }
        values.set(flag, value);
    }
    return values;
}

async function main() {
    const args = parseArgs(process.argv.slice(2));
    const tokens = readFileSync(args.get("--tokens") ?? "tokens.txt", "utf8")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

    return observe({
        tokens,
        connections: Number(args.get("--connections") ?? 20),
        watchSeconds: Number(args.get("--watch") ?? 0),
        timeoutMs: Number(args.get("--timeout") ?? 10) * 1000,
        api: process.env.API ?? "http://localhost:8080",
        origin: process.env.ORIGIN ?? "http://localhost:8081",
        ticketPath: process.env.TICKET_PATH ?? "/v1/ws-tickets",
        wsPath: process.env.WS_PATH ?? "/v1/ws",
        field: process.env.HELLO_FIELD ?? "gateway",
    });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    try {
        process.exitCode = await main();
    } catch (error) {
        console.error(error.message);
        process.exitCode = 1;
    }
}
