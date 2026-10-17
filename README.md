# FireWatch AI

FireWatch AI is a satellite-observation triage dashboard that loads near-real-time fire detections from NASA FIRMS, displays priority-ranked observations, and lets authorities record local review feedback. It is a decision-support prototype: satellite hotspots and browse imagery do not confirm a fire or replace local emergency procedures.

## Live application

- Vercel app: https://vyom-kohl-six.vercel.app/
- Data: NASA FIRMS VIIRS Suomi-NPP near-real-time feed for the South Asia bounding box, latest 24 hours.
- Imagery: NASA Global Imagery Browse Services (GIBS), MODIS Terra corrected reflectance true color, selected by observation date.
- API key: configure `FIRMS_MAP_KEY` as a Vercel Production Environment Variable. The key is read only by the serverless function in `api/firms.js`; do not place it in browser code or commit it to Git.

## Features

- Live FIRMS observations with satellite, acquisition time, confidence, and fire radiative power.
- Map, searchable/filterable observation table, and explainable priority ordering.
- A NASA satellite-imagery action on each review-queue row, plus a link to NASA Worldview.
- Authority review notes, reviewed-decision list, and CSV export.
- NASA data refresh on demand; the server response is cached briefly to respect upstream limits.
- While the page is open, new red-tier observations are checked every five minutes and emailed as a human-review digest through FormSubmit. The first load sets a baseline, and every message says detections are not verified fires.

## Run locally

This is a static HTML/CSS/JavaScript site with Vercel serverless functions. Install the Vercel CLI, set `FIRMS_MAP_KEY` in the local Vercel environment, then run `vercel dev` from this directory.

## Limitations

- FIRMS points are thermal-anomaly detections. They may be delayed, obscured, or caused by non-wildfire heat sources.
- NASA GIBS provides satellite browse imagery, not close-up ground photographs; coverage, resolution, and cloud conditions vary.
- The priority score is an unvalidated review heuristic, not a probability or severity estimate.
- The authority email allowlist in the public demo does not verify identity. Reviews currently persist in that browser only.
- Email delivery is best-effort and requires FormSubmit recipient activation; no emergency dispatch is sent.

## Attribution

Active-fire observations are provided by NASA LANCE FIRMS. Imagery is provided by NASA Global Imagery Browse Services (GIBS), part of NASA Earth Science Data and Information System. Please see the NASA [FIRMS](https://firms.modaps.eosdis.nasa.gov/) and [GIBS](https://nasa-gibs.github.io/gibs-api-docs/) documentation.
