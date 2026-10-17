export default function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ error: "Method not allowed" });
  }

  return response.status(200).json({
    status: "healthy",
    app: "FireWatch AI",
    version: "3.0.0",
    timestamp: new Date().toISOString(),
    deployment: "vercel-static-dashboard",
    data_mode: "NASA FIRMS VIIRS SNPP NRT"
  });
}
