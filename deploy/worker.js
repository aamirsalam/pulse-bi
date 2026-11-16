// Password check in front of a published dashboard (Cloudflare Worker).
// The password is the DASHBOARD_PASSWORD secret (wrangler secret put
// DASHBOARD_PASSWORD --name <worker>); without it every request is refused.
// Used by `python -m pulse_bi --customer <name> publish`.

const USERNAME = "owner";

async function sha256(text) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

async function passwordMatches(request, password) {
    const header = request.headers.get("Authorization") || "";
    if (!header.startsWith("Basic ")) return false;

    let given;
    try {
        given = atob(header.slice(6));
    } catch {
        return false;
    }

    // Compare hashes so both sides are the same length for timingSafeEqual.
    return crypto.subtle.timingSafeEqual(
        await sha256(given),
        await sha256(`${USERNAME}:${password}`),
    );
}

export default {
    async fetch(request, env) {
        if (!env.DASHBOARD_PASSWORD) {
            return new Response("Dashboard password not set.", { status: 503 });
        }

        if (!(await passwordMatches(request, env.DASHBOARD_PASSWORD))) {
            return new Response("Password required.", {
                status: 401,
                headers: { "WWW-Authenticate": 'Basic realm="Dashboard", charset="UTF-8"' },
            });
        }

        const response = await env.ASSETS.fetch(request);
        const page = new Response(response.body, response);
        // Don't leave business figures in shared caches.
        page.headers.set("Cache-Control", "private, no-store");
        page.headers.set("X-Robots-Tag", "noindex");
        return page;
    },
};
