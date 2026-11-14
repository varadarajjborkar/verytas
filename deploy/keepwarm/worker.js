// Keeps the free Render API awake. Render stops a free service after 15 minutes without a request and the
// next visitor then waits about a minute for it, so a Cloudflare cron (free) asks for /health every 10.
// /health never touches the database, so Neon's compute still sleeps when nobody is using the demo.
const TARGETS = ["https://verytas-api.onrender.com/health"];

export default {
  // One free service running all month uses about 730 of Render's 750 free hours, so there is room for this
  // one only. A failure is logged (Workers logs) so a renamed or broken service does not go unseen.
  async scheduled(_event, _env, ctx) {
    ctx.waitUntil(Promise.all(TARGETS.map(async (url) => {
      try {
        const res = await fetch(url, { headers: { "user-agent": "verytas-keepwarm" }, signal: AbortSignal.timeout(90_000) });
        if (!res.ok) console.log(`keepwarm ${url}: HTTP ${res.status}`);
      } catch (err) {
        console.log(`keepwarm ${url}: ${err}`);
      }
    })));
  },
};
