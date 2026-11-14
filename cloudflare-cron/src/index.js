// Cron Trigger de Cloudflare: cada minuto dispara el tick de la API de FríoTrack.
// `API_URL` y `CRON_TOKEN` son secretos del Worker (`wrangler secret put`).
export default {
  async scheduled(_evento, env) {
    const respuesta = await fetch(`${env.API_URL}/simulador/tick`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.CRON_TOKEN}` },
    });
    const cuerpo = await respuesta.text();

    if (!respuesta.ok) {
      console.error(`Tick respondió ${respuesta.status}: ${cuerpo}`);
      // Lanzar el error marca la ejecución como fallida en `wrangler tail`.
      throw new Error(`El tick falló con status ${respuesta.status}`);
    }

    const { lecturas, saltadas } = JSON.parse(cuerpo);
    console.log(`Tick ok: ${lecturas} lecturas; saltadas: ${saltadas}`);
  },
};
