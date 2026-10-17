"""
Vercel Serverless Function Entrypoint for FireWatch AI.
Provides public telemetry endpoints and an interactive cloud portal.
"""

from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime

PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FireWatch AI - Satellite Fire Triage Cloud Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --card-bg: #131b2e;
            --border: #233152;
            --primary: #ff334b;
            --accent: #38bdf8;
            --success: #10b981;
            --text: #f1f5f9;
            --text-dim: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            line-height: 1.6;
        }
        header {
            border-bottom: 1px solid var(--border);
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(19, 27, 46, 0.6);
            backdrop-filter: blur(10px);
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-weight: 700;
            font-size: 1.25rem;
            letter-spacing: -0.02em;
        }
        .brand-badge {
            background: rgba(255, 51, 75, 0.15);
            color: var(--primary);
            border: 1px solid var(--primary);
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
        }
        main {
            max-width: 1080px;
            margin: 3rem auto;
            padding: 0 1.5rem;
            width: 100%;
        }
        .hero {
            text-align: center;
            margin-bottom: 3.5rem;
        }
        .hero h1 {
            font-size: 2.75rem;
            font-weight: 800;
            margin-bottom: 1rem;
            line-height: 1.2;
            background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .hero p {
            font-size: 1.15rem;
            color: var(--text-dim);
            max-width: 680px;
            margin: 0 auto 2rem;
        }
        .action-group {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.85rem 1.75rem;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            font-size: 1rem;
        }
        .btn-primary {
            background: linear-gradient(135deg, #ff334b 0%, #d32f2f 100%);
            color: white;
            box-shadow: 0 4px 20px rgba(255, 51, 75, 0.35);
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(255, 51, 75, 0.5);
        }
        .btn-secondary {
            background: var(--card-bg);
            color: var(--text);
            border: 1px solid var(--border);
        }
        .btn-secondary:hover {
            background: #1e293b;
            border-color: #3b82f6;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.75rem;
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--accent));
        }
        .card h3 {
            font-size: 1.15rem;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .card p {
            color: var(--text-dim);
            font-size: 0.95rem;
            margin-bottom: 1.25rem;
        }
        .code-block {
            background: #060911;
            padding: 0.85rem 1rem;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.825rem;
            color: #38bdf8;
            border: 1px solid #1a2235;
            overflow-x: auto;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 0.9rem;
        }
        .metric-label { color: var(--text-dim); }
        .metric-value { font-weight: 600; font-family: 'JetBrains Mono', monospace; }
        footer {
            border-top: 1px solid var(--border);
            padding: 1.5rem 2rem;
            text-align: center;
            color: var(--text-dim);
            font-size: 0.875rem;
        }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <span>🛰️ FireWatch AI</span>
            <span class="brand-badge">CLOUD DEPLOYMENT</span>
        </div>
        <div style="font-size: 0.875rem; color: var(--text-dim);">
            Deployed by: <b style="color: var(--text);">mjdp4317@gmail.com</b>
        </div>
    </header>

    <main>
        <div class="hero">
            <h1>Autonomous Satellite Active Fire Triage & ERS Dispatch</h1>
            <p>
                Near-real-time Earth observation telemetry powered by NASA FIRMS (MODIS & VIIRS), 
                high-resolution optical satellite snapshots, spatial Haversine clustering, and location-aware 
                emergency response authority routing.
            </p>
            <div class="action-group">
                <a href="https://github.com/jitendradurgaprasad/VyomTech" class="btn btn-primary" target="_blank">
                    <span>⚡ View GitHub Repository</span>
                </a>
                <a href="https://ntfy.sh/vyom_firewatch_alerts_mjdp" class="btn btn-secondary" target="_blank">
                    <span>🔔 Open Live Push Stream</span>
                </a>
                <a href="/api/health" class="btn btn-secondary">
                    <span>🩺 System Health API</span>
                </a>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h3>🛰️ Earth Observation Telemetry</h3>
                <p>Real-time thermal anomaly streams with calibrated Radiative Power (FRP) and confidence scoring.</p>
                <div class="metric-row">
                    <span class="metric-label">Satellite Sensors</span>
                    <span class="metric-value">NASA Terra, Aqua, VIIRS</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Spatial Resolution</span>
                    <span class="metric-value">375m (VIIRS) / 1km (MODIS)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Priority Engine</span>
                    <span class="metric-value">5-Factor Linear Saturation</span>
                </div>
            </div>

            <div class="card">
                <h3>🛡️ Emergency Response System (ERS)</h3>
                <p>Location-aware geodesic routing linking detected fire coordinates directly to the closest emergency unit.</p>
                <div class="metric-row">
                    <span class="metric-label">Designated ERS Unit</span>
                    <span class="metric-value">Regional Emergency Command</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Response Email</span>
                    <span class="metric-value">mjdp8086@gmail.com</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Emergency Contacts</span>
                    <span class="metric-value">9705447958, 7793956633</span>
                </div>
            </div>

            <div class="card">
                <h3>⚡ Cloud Execution Options</h3>
                <p>Run the full interactive dashboard locally with 1-click batch runner or deploy to Streamlit Community Cloud.</p>
                <div class="code-block">
                    git clone https://github.com/jitendradurgaprasad/VyomTech.git<br>
                    run.bat
                </div>
            </div>
        </div>
    </main>

    <footer>
        <p>FireWatch AI &copy; 2026 VyomTech. Developed by Medisetti Jitendra Durga Prasad (mjdp4317@gmail.com).</p>
        <p style="margin-top: 0.25rem; font-size: 0.8rem; color: #64748b;">Telemetry acknowledged from NASA LANCE ESDIS FIRMS.</p>
    </footer>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless HTTP Handler."""

    def do_GET(self):
        if self.path in ("/api/health", "/api/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = {
                "status": "healthy",
                "app": "FireWatch AI",
                "version": "2.0.0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "repository": "https://github.com/jitendradurgaprasad/VyomTech",
                "operator": "mjdp4317@gmail.com",
                "emergency_contact": "mjdp8086@gmail.com",
                "hotlines": ["+91-9705447958", "+91-7793956633"],
                "live_push_stream": "https://ntfy.sh/vyom_firewatch_alerts_mjdp"
            }
            self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PORTAL_HTML.encode("utf-8"))
