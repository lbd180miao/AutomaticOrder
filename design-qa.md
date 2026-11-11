# Device status design QA

final result: passed

Selected target: first displayed concept, exec-7c5dd378-45d4-4e5a-9400-5d09a7ab2712.png.
Route: /devices/status/. Desktop comparison: 1487 × 1058 pixels, same all-offline/collapsed state. Evidence: audit/device-status-comparison.png (reference left, implementation right), audit/device-status-list-desktop.png. Narrow-screen check: 390 × 844 CSS pixels, audit/device-status-list-mobile.png.

Iteration 1: P2 typography hierarchy was too small; P2 alarm label inherited low-contrast dark-theme colors. Increased desktop heading, navigation, device/status labels and actions; explicitly set alarm foreground and background. Thinned local Tabler icon strokes.

Iteration 2: Re-captured and inspected paired images. No remaining P0/P1/P2 issues. Light navigation, blue selected underline, inline summary, right-aligned actions, three flat divided rows, text-and-color states and whitespace match the selected direction. Text and controls are readable in the full-resolution comparison. No raster assets or image scaling issues. Local licensed Tabler symbols replace generated concept icons; font rendering and the outline brand mark remain minor visual differences (P3).

Interaction checks: device disclosure opens and closes; maintenance menu exposes all four links; details remain expanded across automatic refresh; no browser console errors; no broken images; 390px viewport has 390px document width. Production start/stop was not actuated in browser. Existing control and health test suite: 17 passed. Real device status remains offline as reported by the backend.

Styles are scoped to this page. No deployment created.


## Rack type mapping library extension

2026-11-11: Added the requested editable mapping section below the device list using the existing light list style. Browser verified initial 20 rows, requested three standard entries first, code search, edit form population, save and reload, new form, cancellation; console has no errors. Screenshot: audit/rack-type-mapping.png. CRUD, INT bounds, CSRF, missing/deleted/disabled mapping rejection and actual PLC memory-transport handshake checked in 36 passing tests. No physical PLC writes were made during verification. Local DB backed up before applying mes migrations 0005 and 0006. MES-only migration drift check passed; unrelated pre-existing production/workflow drift was left unchanged.

# MES records simplification QA — 2026-11-11

final result: passed

Scope: desktop implementation of selected option 3 at /mes/records/.
Source: C:/Users/11410/.codex/generated_images/01a1ca8d-37f4-77b3-88bd-873967e65173/exec-d47efbe6-6889-496d-9423-75962d16bf32.png (1487 x 1058).
Implementation: D:/workspace2/AutomaticOrder/audit/mes-desktop.png (1472 x 1047); requested CSS viewport 1487 x 1058. Comparison: audit/mes-comparison.png, implementation normalized to source dimensions. State: first interface selected, empty input, response collapsed, sample bindings visible.

Full-view and readable table/form comparison: two stacked sections, blue selected interface tab, shared form, collapsed response and three-column bindings table match the selected hierarchy. Existing application navigation and smaller production typography are intentionally retained. Real records continue below the two examples; search and pagination are necessary for existing local data. Corrected concept semantics: MES bin code belongs to the rack, not individual physical slots. No new image assets were required.

Fidelity surfaces: existing Chinese sans-serif typography and clear heading hierarchy; aligned form/table spacing; navy/blue/light-gray tokens; no stretched or substituted image assets; actual interface names and rack-level bin-code content. No actionable P0/P1/P2 desktop findings. P3: typography is more compact than the generated concept.

Browser checks completed: all three interface tabs switch, product barcode appears only for the binding interface, empty required rack input is invalid, response disclosure opens, no horizontal overflow at desktop viewport, no browser console errors. Three Django tests pass: all 55 products remain grouped, empty racks and preview fixtures, product search preserves complete rack contents, successful current-cycle bin receipts and stale-receipt exclusion, and all three manual API actions dispatch to mocked services. Django system check passes.

Limits: live company MES submissions intentionally not performed. Narrow-screen browser verification and viewport reset could not be completed after the browser tool became unavailable. Responsive CSS is implemented but this report only passes the observed desktop scope. Existing device QA above remains unchanged.

## MES latest correction
User supplied explicit three-card reference. Replaced sidebar/tabs with three independent forms and response panels; table renders only two example rack records. Bin code is read-only because the existing MES contract returns it on sealing. System check, JS syntax check, and three backend tests pass. Latest browser visual verification blocked: Computer Use repeatedly reported user input and minimized window; no further input attempted. Earlier desktop screenshots do not represent this latest revision.
final result: blocked
