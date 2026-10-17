function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (!lines[0] || !/latitude\s*,\s*longitude/i.test(lines[0])) throw new Error("NASA FIRMS returned an error instead of CSV data; verify the MAP_KEY and query configuration");
  if (lines.length < 2) return [];
  const headers = lines.shift().split(",").map(v => v.trim());
  if (!headers.includes("latitude") || !headers.includes("longitude")) throw new Error("NASA FIRMS returned an unexpected CSV format");
  return lines.map(line => {
    const fields = [];
    let value = "", quoted = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"' && line[i + 1] === '"' && quoted) { value += '"'; i++; }
      else if (c === '"') quoted = !quoted;
      else if (c === "," && !quoted) { fields.push(value); value = ""; }
      else value += c;
    }
    fields.push(value);
    const row = Object.fromEntries(headers.map((h, i) => [h, fields[i] ?? ""]));
    const num = v => v === "" ? null : Number(v);
    return {
      latitude: num(row.latitude), longitude: num(row.longitude),
      brightness: num(row.bright_ti4 ?? row.brightness), scan: num(row.scan), track: num(row.track),
      acq_date: row.acq_date, acq_time: String(row.acq_time ?? "0000").padStart(4, "0"),
      satellite: row.satellite, _instrument: row.instrument, confidence: row.confidence,
      frp: num(row.frp), daynight: row.daynight, _source: "NASA FIRMS VIIRS SNPP NRT",
      _id: `${row.satellite}-${row.acq_date}-${row.acq_time}-${row.latitude}-${row.longitude}`
    };
  }).filter(r => Number.isFinite(r.latitude) && Number.isFinite(r.longitude));
}

export default async function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ error: "Method not allowed" });
  }
  const key = process.env.FIRMS_MAP_KEY;
  if (!key) return response.status(503).json({ error: "NASA FIRMS API key is not configured on this deployment" });
  const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${encodeURIComponent(key)}/VIIRS_SNPP_NRT/54,5.5,102,40/1`;
  try {
    const result = await fetch(url, { headers: { Accept: "text/csv" }, signal: AbortSignal.timeout(15000) });
    const csv = await result.text();
    if (!result.ok) throw new Error(`NASA FIRMS request failed (${result.status})`);
    if (/invalid map key|map key.*invalid|error:/i.test(csv.slice(0, 500))) throw new Error("NASA FIRMS rejected the configured API key or query");
    const rows = parseCsv(csv);
    response.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=120");
    response.setHeader("X-Data-Source", "NASA FIRMS VIIRS_SNPP_NRT");
    return response.status(200).json({ source: "NASA FIRMS VIIRS SNPP NRT", region: "South Asia", fetchedAt: new Date().toISOString(), rows });
  } catch (error) {
    return response.status(502).json({ error: error.message || "Could not retrieve NASA FIRMS data" });
  }
}
