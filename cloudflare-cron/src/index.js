// Cron Trigger de Cloudflare: cada minuto dispara el tick de la API de FríoTrack.
// `API_URL` y `CRON_TOKEN` son secretos del Worker (`wrangler secret put`).
export default {
  async scheduled(_evento, env) {
    const base = env.API_URL.replace(/\/+$/, "");
    const respuesta = await fetch(`${base}/simulador/tick`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CRON_TOKEN}` },
      // El cold start de Render puede tardar ~1 min; el backend deduplica
      // los ticks solapados con su ventana de 30 s.
      signal: AbortSignal.timeout(90_000),
    });
    const cuerpo = await respuesta.text();

    if (!respuesta.ok) {
      console.error(`Tick respondió ${respuesta.status}: ${cuerpo}`);
      // Lanzar el error marca la ejecución como fallida en `wrangler tail`.
      throw new Error(`El tick falló con status ${respuesta.status}`);
    }

    let datos;
    try {
      datos = JSON.parse(cuerpo);
    } catch {
      console.log(
        `Tick respondió ${respuesta.status} con un cuerpo que no es JSON: ${cuerpo.slice(0, 200)}`,
      );
      return;
    }

    console.log(`Tick ok: ${datos.lecturas} lecturas; saltadas: ${datos.saltadas}`);
  },
};
