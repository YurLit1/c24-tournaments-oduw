// Calls to the system through nginx: base address, access token, Idempotency-Key, Problem Details.
// Serve the client outside Compose:  python -m http.server 8081 --bind 127.0.0.1 --directory client

export const API = localStorage.getItem("api") ?? "http://localhost:8080";

export class Problem extends Error {
    constructor(status, body) {
        super(body?.title ?? `HTTP ${status}`);
        this.status = status;
        this.body = body;
    }
}

let token = sessionStorage.getItem("token");

export function setToken(value) {
    token = value;
    if (value) {
        sessionStorage.setItem("token", value);
    } else {
        sessionStorage.removeItem("token");
    }
}

export const loggedIn = () => Boolean(token);

export async function call(method, path, {body, idempotencyKey, headers = {}} = {}) {
    const reply = await fetch(API + path, {
        method,
        headers: {
            ...(body !== undefined ? {"Content-Type": "application/json"} : {}),
            ...(token ? {Authorization: `Bearer ${token}`} : {}),
            ...(idempotencyKey ? {"Idempotency-Key": idempotencyKey} : {}),
            ...headers,
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const type = reply.headers.get("content-type") ?? "";
    const data = type.includes("json") ? await reply.json() : await reply.text();
    if (!reply.ok) {
        throw new Problem(reply.status, typeof data === "object" ? data : {title: data});
    }

    return {status: reply.status, headers: reply.headers, data};
}

export const newKey = () => crypto.randomUUID();

export async function login(loginName, password) {
    const {data} = await call("POST", "/v1/auth/login", {body: {login: loginName, password}});
    setToken(data.access_token);
    return data;
}

export async function logout() {
    try {
        await call("POST", "/v1/auth/logout");
    } finally {
        setToken(null);
    }
}
