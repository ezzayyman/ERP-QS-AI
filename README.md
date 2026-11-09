# GMI FloorTakeoff

Legend-aware flooring quantity takeoff and BOQ for GMI Design and Implementation LLC (Dubai).

The application reads a floor-finish drawing as a structured document. It interprets the drawing's own
finishes legend, finds where each finish occurs on the plan, traces the finish boundaries from the drawing
geometry, and calibrates from the drawing's figured dimensions. The results are offered for review; only
reviewed and accepted measurements become BOQ quantities, each traceable to its source region, legend entry
and sheet.

- Why the previous version placed and measured regions wrongly: [`docs/DIAGNOSIS.md`](docs/DIAGNOSIS.md)
- Results on the Boutique Kitchen reference drawing: [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md)

## Stack

React 19 + TypeScript + Vite (frontend), FastAPI + SQLAlchemy/SQLite (backend), PyMuPDF (PDF vectors and
rendering), Shapely (geometry), OpenCV/NumPy (hatch coverage, raster fallback), openpyxl / ReportLab (exports).
No external AI service is used. Classification and geometry are deterministic and testable.

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Import | `document_import.py`, `routes/drawings.py` | Renders pages for display. Records each page's canonical coordinate space. Queues background analysis (`jobs.py`). |
| Vector extraction | `vector_extract.py` | Fills intersected with their active clip paths (even-odd / non-zero), kept in paint order. Strokes as arrays. Text spans and blocks. Images. All in rotated display space (PDF points). Cached per file hash. |
| Legend | `legend.py`, `legend_rows.py`, `ocr.py` | Finds the legend heading and parses it in one of two ways. **Tables** with a column-header row (code / image / symbol / description) are parsed by columns and rules. **Header-less legends** (title, category sub-headings, CODE · description · swatch rows, partial or no rules) are parsed by code-column alignment, row bands, same-line and continuation text, category headings, and swatches associated by row geometry (never by colour). Image-based legends are read with Tesseract OCR (results always marked for review); if OCR is missing the stage reports why. Each row yields code, description, category, indicator kind (area / linear / raster / text-only), swatch box and colour, and a symbol signature. Tag-notation keys are reported, not added. Every stage reports its own status. |
| Calibration | `calibration_engine.py` | Figured dimensions measured tick-to-tick (not along overshooting dimension lines). Mode-seeking consensus, comparison with the stated scale, explicit notes. A user must confirm the calibration. |
| Detection | `finish_detection.py` | Legend fill colours matched with CIEDE2000. Paint-order visibility where only finish fills (and dark structure) occlude; annotations and furniture never remove floor. Composite symbols (e.g. a border band) are resolved by ray enclosure. Same-colour finishes are separated by hatch signature. Hatch-only finishes are traced by hatch coverage, with edges refined to the line ends. Linear finishes come from their line style, with dash gaps bridged. Code labels corroborate or conflict. Scope comes from phrase rules (e.g. "BY OTHERS"). |
| Raster fallback | `raster_detection.py` | For scanned or flattened sheets: local-mean CIELAB matching against legend swatches or user-picked plan samples. Ambiguous pixels are left unassigned. Never rated above "medium". |
| Review | `takeoff_service.py`, `routes/takeoff.py` | Candidates are stored apart from measurements. A candidate is accepted only with a resolved finish and scope, and never on top of accepted area (overlap → 409, or clip). Supports edit, split, merge, fill openings and reclassify, with server-side undo/redo and an audit trail. |
| Quantities | `quantities.py`, `boq_export.py` | Accepted regions only, recomputed from geometry and the active calibration. Grouped by code + unit + scope. Waste, packages and rates come from the legend entry or a linked catalogue item, with saved adjustments surviving regeneration. A signature check marks an approved BOQ "needs review" when measurements change. Excel/CSV/PDF/ERP exports include a region register. |
| Validation | `validation_report.py`, `backend/tools/validate_reference_drawing.py` | Compares with *independent* reference quantities (e.g. PlanSwift). States plainly when none exist. |

### Coordinates

All geometry is stored in a page's canonical space:
- `pdf_pt`: PDF points, rotated display space.
- `image_px`: original raster pixels.
- `render_px`: legacy pages created before this pipeline.

The page image is drawn stretched to exactly `source_width × source_height`, so render resolution and device
pixel ratio cannot shift geometry. The single view transform lives in `src/utils/viewTransform.ts`.
Calibration is stored as units per metre in the same space.

Legacy pages can be converted explicitly ("Convert to PDF coordinates" in the review panel). Their geometry and
calibration are rescaled by the exact render ratio, so areas do not change.

### Review workflow (UI: Takeoff review panel)

- **A · Legend:** correct codes and descriptions, set default scope, then confirm or reject entries.
- **B–E · Candidates:** each candidate shows its evidence, boundary quality and conflicts. Choose the finish and scope, then accept or reject. Bulk accept applies only to classified candidates and still enforces every check.
- **Scale:** review the figured-dimension evidence and confirm, or calibrate manually.
- **F · Approval:** approve the BOQ from accepted measurements. This is blocked while calibrations are unconfirmed or scopes unresolved.

## Run

```bash
py -3.12 -m pip install -r requirements.txt
```

```bash
py -3.12 run_local_backend.py
```

```bash
npm install
```

```bash
npm run dev
```

Backend on http://localhost:8000 (docs at `/docs`), frontend on http://localhost:5173. `GMI_STORAGE_DIR`
selects another storage root (database, drawings, renders). The Vite proxy target can be overridden with
`GMI_API_TARGET`.

### Database migrations

On start-up `migrations.py` applies pending, numbered migrations, recorded in `schema_migrations`. Before applying
them it copies the SQLite file to `backend/storage/backups/`. Migrations only add columns and tables; existing
geometry is preserved, and legacy regions are marked `source = legacy_*`.

## Tests

```bash
npm run test:backend
```

```bash
npm run test:frontend
```

Backend tests run against a temporary database and storage directory, never the live data:
- Synthetic PDFs with analytically known answers (clip paths, even-odd holes, composite symbols, same-colour finishes, hatch-only finishes, dashed lines, dimension ticks, /Rotate 0/90/270, legends in different corners, missing descriptions, duplicate codes, raster symbols).
- Render-alignment checks.
- The end-to-end API workflow.
- Fixture points on the Boutique Kitchen drawing.

The frontend test checks zoom, pan, resize and DPR invariance of the view transform.

## Known limitations

- **No independent reference yet.** Quantities on the reference drawing have not been compared with an independent PlanSwift takeoff (see the validation report).
- **Hatch-only finishes have approximate boundaries.** Those without a vector outline (e.g. TL-03, LL on the reference sheet) follow hatch-line ends, so concave corners narrower than the closing radius must be checked in review.
- **Labels are matched by position only.** Leader lines are not traced; tags away from their region are listed as unmatched.
- **Scanned legends rely on Tesseract.** Image-based legends need Tesseract (found on PATH, in `C:\Program Files\Tesseract-OCR`, or via `GMI_TESSERACT_CMD`) plus `pytesseract`. OCR text is always marked for review: letter/digit confusions in codes such as FIC-01A for FTC-01A, or 018 for 01B, cannot be corrected automatically. Photographic swatches are recorded but not used to classify vector plans.
- **DWG is not read directly.** Export to PDF (preferred, keeps vectors) or DXF.
- **Two older surfaces are not on the new pipeline.** The original contour room detector (`cv_engine.py`) remains as a boundary-only assist, and the standalone `gmi_floortakeoff_app.py` is a separate legacy file that has not been migrated.
