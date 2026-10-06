# Review: Robodog Factory Inspection Demo Plan

Reviewed document: `docs/robodog-bim-demo-plan.md`
Review basis: plan document, repository state (no code yet), and spot-checks of the source videos with ffprobe.

## Overall assessment

This is a genuinely good plan. Unusual for a demo plan, it gets the hard parts right:

- **Honest scoping** — it repeatedly distinguishes representative vs. measured, AI-suggested vs. reviewed. That is exactly the language construction and BIM professionals will probe with.
- **Clean traceability chain** — `video timestamp → observation → space/asset ID → issue` is the product's core value proposition, and the data model supports it.
- **Geometry/evidence separation** — storing evidence apart from the model so the model can be swapped later is architecturally correct.
- **Testable acceptance criteria** — each one is verifiable.

The plan's weakness is not execution mechanics; it is **positioning**. Two issues dominate.

## The two big gaps

### 1. The demo does not actually integrate with BIM software

The objective says "integrate with BIM software," but the plan builds a standalone web viewer (That Open components plus a custom database). Autodesk Platform Services (APS) is deferred to a footnote. For a construction audience, that reads as prototype, not integration. Cheap, high-credibility fixes:

- **Add BCF export as a core deliverable.** BCF 2.1 is the open buildingSMART standard for issues anchored to model elements, readable in Navisworks, Solibri, Revizto, BIMcollab, and Revit (via add-ins). Exporting reviewed issues to BCF is a small amount of work and produces a "here is the artifact a real BIM tool consumed" moment — far more persuasive than an animated web model.
- **Add model stations a construction audience expects:** gridlines (A1, B2, ...), a level naming convention, and room/space tags with names. This costs almost nothing in IfcOpenShell and instantly makes the model read as "BIM" instead of "3D game scene."
- **Use construction-grade issue fields:** discipline (Structural/MEP/Safety), severity matrix, due date, and a workflow of open → assigned → resolved → verified/closed. The demo report should look like a punch list a general contractor would recognize.
- Keep the APS/ACC Issues API as the stated near-term integration (APS Data Management/Issues API has issue-creation endpoints), but BCF is the portable first step.

### 2. Factory footage vs. construction audience

The plan picks a factory because that is the footage available — sensible — but it never tells the presenter how the story lands with a construction audience. Two concrete moves:

- **Reframe the story as commissioning/handover.** A new manufacturing facility *is* an industrial construction project, so the pitch becomes: "during handover and turnover of a constructed facility, robot patrols create traceable as-built inspection evidence linked to the model." That sits squarely in construction territory (snagging/punch lists, turnover documentation) without pretending the videos are a construction site.
- **Add a one-page translation table** mapping each demo beat to construction uses: aisle → egress corridor, cables on floor → trip hazard, storage racks → scaffolding/stored materials, machine → installed equipment. This is the slide that makes the demo land.

## Content and scope improvements

- **Promote "searchable footage" from optional to at least a minimal core.** It is the strongest AI wow-moment and cheap in 2026: precompute CLIP embeddings over sampled frames and support a few curated queries ("cables on floor", "storage racks"). Search is the feature that justifies the robot/AI story to non-technical buyers; cut "patrol coverage" views before search.
- **Tighten the observation curation process.** The plan admits only three frames per video were sampled. The demo lives or dies on four to six visually legible observations. Add a step 0: a full inventory pass — thumbnails at one frame per five seconds, scene detection, and selection of the most visually obvious issues.
- **Record wall-clock patrol time explicitly.** ffprobe on two clips shows 1920×1080, 30 fps, ~120 seconds each (about 20 minutes total, matching the plan), but **no embedded `creation_time`** in the container metadata. Capture time must come from file timestamps or manual documentation, so add `captured_at` and `recording_device` fields to the Video record early.
- **Add a narrative/storyboard section.** The plan describes features but not talking points. Add a time-boxed 7-minute script with a per-step message ("walkdowns today are manual, photos end up in chat apps, none of it links back to the model"), plus two variants: a 5-minute executive cut and a 10-minute technical cut.
- **Pre-record a fallback screencast** of the entire flow. One hour of work buys live-demo insurance.
- **Check footage reuse rights and worker privacy.** These are real factory recordings with workers visible. For public showing, blur faces in the clips used or select segments without identifiable people, and confirm redistribution rights for the download source. Construction firms will ask.
- **Add a risk register.** Currently only "limits." Add: footage-quality surprises, a BIM professional calling out model fidelity, live failure (mitigated by the fallback screencast), and AI producing a wrong suggestion mid-demo — the existing review/correct beat already handles this, so stage it deliberately.
- **Add a production-vision slide.** One diagram showing the real ingestion pipeline (robot dock upload → indexing → patrol record → BIM link). The demo proves the workflow exists; the vision slide proves it scales to a fleet and to Autodesk/Procore ecosystems.
- **Make provenance visible in the UI, not just the docs.** The acceptance criteria mention distinguishing AI-suggested from reviewed and representative from measured; design that as a badge on every mapping (⚠ illustrative route vs. measured) and every observation (AI-suggested vs. reviewed). Show it, don't just state it.

## Smaller fixes

- **Effort estimates and dates** per phase, with an explicit cut-line: searchable footage and coverage views die first under time pressure.
- **Route replay disclaimer in the viewer itself.** "Illustrative replay, not robot telemetry" appears in the plan; surface the same wording in the UI so no audience member infers LiDAR-grade positioning.
- **Check whether the clips form one continuous patrol.** Uniform ~2-minute segments suggest robot-created clips. If the same aisle appears in multiple clips, mine it for a cheap "same location, later visit" within-session comparison that foreshadows change detection.
- **Enrich the report export.** The PDF should include timestamp-burnt screenshots, source clip and time, reviewer, status, and — if BCF lands — the BCF file itself, so the PDF becomes the traceability artifact.

## Suggested revised priorities

| Capability | Current plan | Suggested |
| --- | --- | --- |
| BIM-linked walkthrough | Core | Core |
| Visual inspection assistant | Core | Core |
| Equipment evidence register | Core | Core |
| Issue workflow | Core | Core, plus discipline/severity/due-date fields |
| Inspection report + BCF export | Core / absent | Core |
| Searchable footage | Optional | Not-too-late stretch (minimum: a few curated queries) |
| Patrol coverage | Optional | Optional (or cut) |
| Change detection | Later | Later, but mine within-session repeats if present |

## Bottom line

The plan is implementation-sound but underplays the two things that sell it: **real BIM interoperability artifacts** (BCF, grid/level conventions, punch-list fields) and **a story built for the construction audience** (handover/commissioning frame plus a use-case translation table). Fix those, and the remaining gaps are mostly packaging: a discovered-issue curation pass, a demo script, provenance badges, and a risk list.