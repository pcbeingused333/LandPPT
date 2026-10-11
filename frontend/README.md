# LandPPT browser UI

React 19, TypeScript and Ant Design 6. The FastAPI routes still render Jinja
pages and provide their existing APIs; navigation remains normal browser links.

## Development

Requires Node.js 22.12 or later.

```sh
npm ci --prefix frontend
npm run build --prefix frontend
```

Vite writes local assets to `src/landppt/web/static/antd/`. Start the Python app
normally. `npm run dev --prefix frontend` rebuilds on changes; refresh the browser.
Dependencies and generated assets are ignored by Git.

```sh
npm run check --prefix frontend
python -m pytest tests/test_app_ui.py tests/test_antd_ui.py tests/test_antd_projects_ui.py tests/test_antd_account_ui.py tests/test_antd_admin_ui.py tests/test_antd_admin_management_ui.py tests/test_antd_community_ui.py tests/test_antd_images_ui.py tests/test_antd_templates_ui.py tests/test_antd_creation_research_ui.py tests/test_antd_home_generator_ui.py tests/test_antd_presentation_ui.py tests/test_template_package_workspace_ui.py -q
```

Build before installing from source or publishing Python packages. Hatch includes
the generated resources in both wheel and sdist. Docker compiles them in its
Node build stage and copies them into the Python stages.
The build excludes these assets from normal discovery and force-includes them
once, so a wheel built from the source distribution also contains one copy.
Frontend CI validates this source-to-wheel release path before browser checks.

## Page boundaries

`antd_base.html` loads the new shell without legacy page CSS. Its JSON payload
contains explicit public user fields and page data. The entry point loads each
page separately; an error boundary provides a refresh action if loading fails.
The entry module uses one canonical URL without a query string, because lazy
chunks can import shared exports from that entry. Giving the script a different
URL would execute it twice and remount the page. Serve the stable entry with
cache revalidation; the child chunks carry content hashes.

Currently migrated: project dashboard, project library/detail, all five system
configuration tabs, personal profile, credits, login, registration, password reset,
and admin users, redemption codes, OAuth/email configuration, all five community
administration tabs, the public sponsor page, image gallery, image generation,
template management, template selection, project creation, research status, home
and presentation playback (23 of 26 page templates).
The other pages continue using their existing templates until migrated. The
integrated generation workspace now has Ant Design controls and status feedback,
but retains its original controller, slide renderer, monitor and free-template
wizard. This partial migration is not counted as another completed page.

Home uses compact creation/management links, a three-step guide and public provider
information, without new API calls. The existing `/home` redirect remains intact.
The generation workspace reads the controller's hidden control/status adapter
through a MutationObserver and forwards actions to the same bound buttons. React
never writes controller state or renders presentation content. Start/pause/resume,
stop confirmation, completion and partial retry retain their existing contracts;
terminal errors hide stale pause controls, and active unattended runs expose only
the monitor's cancellation control. The adapter is a temporary migration boundary,
to be removed when the controller and free-template wizard are migrated together.

Presentation playback uses Ant Design controls, a thumbnail drawer and bounded
shortcut/cache dialogs without the account shell, including public share links.
Its standalone controller publishes snapshots and actions rather than mutating
control DOM. Generated srcdoc and the existing frame sizing/fit algorithms remain
unchanged. Owner/share narration endpoints, language availability, autoplay timing
and owner-only ten-second refresh retain their API boundaries. Navigation handles
pending preload frames; refreshed data clamps a deleted current page and updates
the revision watermark. Stopping narration ignores late cue replies. Keyboard
shortcuts work after focusing a slide while leaving embedded inputs and open
panels alone. Panel closure restores focus; the compact toolbar auto-hides after
inactivity while subtitles remain visible. Mobile narration uses two control rows.
Browser fixtures isolate cues/audio; real TTS and audio playback remain deployment
integration checks.

Project creation uses a compact content/settings form and a persistent submit
action on small screens. The existing multipart creation route receives the
same defaults, guidance, file/URL precedence and admin-only unattended settings.
Published package versions are loaded on demand; quick mode selects SVG and
blocks submission after a failed catalogue read. Invalid uploads are skipped,
failed creation keeps its draft, and an already-created project has a recovery
link. Research status and reports load independently with retry; research submits
the topic and language as query parameters required by the existing FastAPI
endpoint. Waiting shows actual elapsed time. Report deletion requires confirmation
and retains the dialog on failure. Browser fixtures never call a real AI service.

The settings catalogue remains in the server-rendered `settingsBlueprint`
template during migration. This retains the existing Jinja permission conditions,
labels, options, bounds and field names. It is inert: its styles, scripts and
inline event handlers do not run. `settings-schema.ts` reads only field metadata;
React owns the visible controls and all new interactions. New requests use the
same API URLs, methods and payload shapes. The Jev API key remains omitted when
left empty so the backend retains its saved secret.

Shell notices and notification polling still use the existing services in their
own DOM containers. Page forms, dialogs and feedback use Ant Design. Settings
cancel pending requests on unmount, retain edits during an initial read, and
prevent concurrent saves. Keyboard focus stays in dialogs and returns to the
trigger after asynchronous tests.

Project lists share one table/mobile-card collection and action controller.
The dashboard uses compact linked summaries, a recent-project list and an
active-task sidebar that stacks below projects on narrow screens. It shares the
same action controller. Project date payloads use the server's timestamp filter
for both Unix timestamps and datetime values; browser fixtures use that actual
filter and numeric project timestamps.
Filtering and pagination retain the server's route query. Detail outlines use
Ant Design cards/forms/dialogs; structural edits still send the existing
operation payload and synchronize presentation pages through the backend.
Failed saves retain entered values. AI optimization remains an unsaved draft,
and project deletion retains both confirmations on the detail page.

Account and authentication pages retain native HTML POST routes and server
redirects. Provider visibility, registration availability, invite requirements
and credits visibility come from explicit server flags. API Key creation/rotation
and credits actions retain their existing JSON contracts. Failed requests keep
entered values; destructive API Key actions require confirmation. Turnstile loads
its official script only for an active verification form, clears expired tokens
and provides bounded loading with retry. Browser checks use isolated API responses
and a Turnstile lifecycle stub; real email delivery and external OAuth remain
deployment integration checks.

Admin email/OAuth configuration shares compact navigation and sticky save actions.
Initial reads retain fields edited while loading. Save/test actions wait for a
successful configuration read, and concurrent operations are blocked. SMTP and
Resend values survive provider changes. Invite email tests deliberately create
real invitation codes using saved mail settings and run only on an explicit user
action; browser regression fixtures never send real messages.

User and redemption management retain their list query, CSV export and mutation
contracts. Mobile lists use cards; dialogs keep their actions visible. Failed
detail reads block user saves, failed mutations retain input for retry, and
destructive actions require confirmation. Self-deactivation and role removal
stay disabled in the UI, with existing server permission checks unchanged.
Credits controls follow the server feature flag; no billing behavior is changed.

Community administration retains every system default field and the existing
blank-value fallback rules. Model discovery uses the current LandPPT credentials;
silent initial discovery preserves custom model names. Shared operating settings
retain unvisited fields when saved from any tab, and local announcement dates
still become Unix seconds. Invite creation, PATCH activation, unused-code deletion,
paging and CSV export retain their original contracts. Sponsors use bounded
create/edit dialogs, preserve failed inputs and keep deletion confirmation.
The public sponsor page receives only presentation fields from the existing
server-filtered list; its admin preview and visibility checks remain server-owned.

Image gallery uses the existing list query, detail/update endpoints and
multipart uploads. Selection survives pagination; batch operations snapshot the
selected IDs and retain failures for retry. Clear-all still requires two
confirmations. Downloads preserve attachment filenames. Ctrl/Cmd+A and Delete
work in batch mode without intercepting text fields or modal input.
Image generation retains all five providers, width/height/quality payloads and
the existing 20-item browser history key. Waiting shows elapsed time rather than
an estimated percentage. Failed generation keeps the form, and image links retain
their dimension query parameters. Presentation files and backend scope checks are
unchanged. Screenshots and isolated API fixtures cover five window sizes.

Template management and selection share Ant Design catalogues, filtering,
pagination, previews and failure feedback. Ordinary template creation, import,
duplication, default selection and export keep their existing contracts. AI
generation and adjustment remain drafts until explicitly saved; all four reference
modes and the original PPTX export helper are retained. Preview documents keep
their original 1280×720 canvas and are scaled outside the document. Ordinary
preview scripts run in an isolated frame; package previews retain their existing
script-free sandbox. Choice submission is locked until it completes, preserves a
failed choice, and navigates to the existing automatic generation URL.

Package metadata changes remain template-level PATCH requests; published manifests
are not rewritten by the catalogue. JSON/ZIP import, cloning, publication, retirement
and version deletion retain their APIs and ownership controls. Package creation
reads incremental SSE progress and requires a completion event before reporting
success. Stopping reception closes the browser stream; it does not claim that the
server has cancelled creation. Inspect the draft list before retrying.

The versioned package editor and PPTX slot analyser are deliberately retained as
legacy islands, loaded only on an explicit action, with their scoped CSS. Their
version, draft, conflict and streaming contracts are unchanged. Thus the 23-page
count measures migrated page shells/catalogues, not completion of every nested
editor. Their internal Ant Design migration and the three remaining page templates
still need to be completed. Screenshots are in ignored `artifacts/` directories.

## Design constraints

Keep black primary actions, neutral surfaces, 14px body text, 20px page headings,
32px desktop controls and 44px mobile touch targets. Configuration tabs wrap on
phones; long forms retain a sticky save action. Keep presentation HTML/SVG and
iframe styles outside application styling.

Continue migration by page: remaining public pages, then
templates, then streaming generation and editor workspaces.
Remove a page's retired CSS and DOM scripts only when its replacement preserves
its actions, permission visibility and browser regressions. Test built assets,
error/empty states and desktop/mobile geometry. Store screenshots in ignored
`artifacts/` folders.
