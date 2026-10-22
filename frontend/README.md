# LandPPT browser UI

React 19, TypeScript and Ant Design 6. The FastAPI routes still render Jinja
pages and provide their existing APIs. Navigation uses normal browser links,
with client navigation between ordinary application pages and project details.

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
npm run test:controllers --prefix frontend
python -m pytest tests/test_app_ui.py tests/test_antd_ui.py tests/test_antd_settings_performance_ui.py tests/test_antd_settings_models_ui.py tests/test_antd_settings_compact_ui.py tests/test_antd_asset_updates_ui.py tests/test_antd_navigation_ui.py tests/test_antd_projects_ui.py tests/test_antd_project_covers_ui.py tests/test_antd_project_search_ui.py tests/test_antd_pagination_ui.py tests/test_antd_progress_ui.py tests/test_antd_account_ui.py tests/test_antd_email_login_ui.py tests/test_antd_admin_ui.py tests/test_antd_admin_management_ui.py tests/test_antd_community_ui.py tests/test_antd_images_ui.py tests/test_antd_templates_ui.py tests/test_antd_creation_research_ui.py tests/test_antd_creation_workspace_ui.py tests/test_antd_home_generator_ui.py tests/test_antd_home_ui.py tests/test_antd_generator_skeleton_ui.py tests/test_antd_generator_lifecycle_ui.py tests/test_antd_template_wizard_ui.py tests/test_antd_generator_documents_ui.py tests/test_antd_presentation_ui.py tests/test_antd_todo_ui.py tests/test_antd_outline_lifecycle_ui.py tests/test_antd_workspace_stages_ui.py tests/test_antd_editor_ui.py tests/test_antd_editor_lifecycle_ui.py tests/test_antd_editor_media_ui.py tests/test_antd_editor_context_ui.py tests/test_antd_editor_export_ui.py tests/test_antd_editor_share_ui.py tests/test_antd_quick_edit_ui.py tests/test_antd_editor_documents_ui.py tests/test_antd_speech_dialog_mount_ui.py tests/test_antd_remaining_ui.py tests/test_template_package_workspace_ui.py -q
```

Build before installing from source or publishing Python packages. Hatch includes
the generated resources in both wheel and sdist. Docker compiles them in its
Node build stage and copies them into the Python stages.
The build excludes these assets from normal discovery and force-includes them
once, so a wheel built from the source distribution also contains one copy.
Frontend CI validates this source-to-wheel release path before browser checks.
Its browser dependencies are pinned in `tests/requirements-browser.txt`.
Four shards run the complete browser suite without retries or skipped failures;
each uploads its JUnit report and available workspace screenshots. UI checks wait
for committed selection/focus, stream reconnection and final transition colors.
The template workspace also checks wider input fonts at 320px so intrinsic form
widths cannot expand the preview column and push AI controls out of view.

## Page boundaries

`antd_base.html` loads the new shell without legacy page CSS. Its JSON payload
contains explicit public user fields and page data. The entry point loads each
page separately; an error boundary provides a refresh action if loading fails.
`app.js` is a small, versioned loader, separate from the React application. It
reads `manifest.json` with `cache: no-store`, then imports the content-hashed
application entry. Shared chunks refer to that same entry URL, so React mounts
once even if the loader has a release query. This also avoids reusing an old
application entry from HTTP cache after a UI update. Loader, manifest, hashed
entry, CSS and chunks must be deployed together; failed discovery offers a
refresh action instead of silently showing an older interface.

Home, dashboard, projects, creation, templates, images, configuration, project
details, accounts, research and administration reuse the shell, React runtime
and loaded modules when switching pages. Each switch
reads the existing authenticated HTML route with no data cache; only its public
page payload and inert settings/community catalogues are used. Fetched scripts never run.
The current link cancels pending navigation; later clicks abort earlier reads.
Browser history, page titles, menu closure and focus are maintained. The server's
root redirect opens `/home`; that page stays on the showcase even for users with
existing projects. Modified clicks and new tabs remain native.
Authentication redirects, account/role changes, invalid responses and mismatched
CSS release stamps fall back to native navigation. Bump that stamp for UI releases.
Shared list pagination wraps within narrow containers while preserving 44px touch
targets and the existing page, search and status callbacks. Large catalogues are
covered in `tests/test_antd_pagination_ui.py`, including 5 and 100 pages across
project, template, package, image and user lists.
Only the `/projects/:id` root participates; editor, task board, playback,
template-selection workspaces and authentication retain full navigation.
Pagination, filtering and project duplication use the same authenticated
navigation. Outline saves and version restoration still reload authoritative
server state. Navigation warms module code on hover/focus and while idle;
it never prefetches private page data or mounts hidden pages to run their APIs.

The footer reads its version from `frontend/package.json`. GitHub and business
contact links use icons, accessible names and hover/focus tooltips; original
destinations and the conditional sponsor link are retained. UI releases bump the
template resource stamp so existing pages switch to the new build on navigation.

Project details group archive/copy/delete in a click-triggered menu; preview and
editing remain direct actions. Outline cards expose view/edit and a menu for
move/delete, alongside drag sorting. Confirmation cancellation restores focus
to the menu trigger; deletion keeps both confirmations. Shared Ant tokens use
black actions, subtle card depth and distinct hover/focus states. Styling affects
application controls only, not generated HTML/SVG inside presentation frames.

Application page shells/catalogues use Ant Design, including dashboard,
project library/detail, configuration, accounts/password recovery, administration,
community, images, templates, creation/research, home, playback, task board,
generation workspace and PPT editor. The shared error page is also migrated.
Announcements use Ant Alert and the notification center uses an Ant Drawer;
its existing poller, read endpoints and desktop-permission flow remain intact.
Login and registration retain their original black/white split layouts and native
forms, restored from the pre-migration templates. Their dedicated CSS/JavaScript
is shipped with the app; login/register switching, invitation requirements,
OAuth provider flags, email-code cooldown and lazy Turnstile remain supported.
The login account field accepts either username or registered email, using the
existing `username` form key for both web and API login. Email matching ignores
case and surrounding whitespace; exact legacy usernames take precedence.
Password recovery and signed-in account pages continue to use Ant Design.
Project percentages round and clamp at the UI boundary across dashboard,
project lists/details and unattended tasks; API calculation precision is unchanged.
The generator's free-template preparation wizard now uses an Ant modal and
ordinary controls, with fixed confirmation actions and preview/code views.
Generation and template preparation have independent controllers and Ant views.
The PPT editor has a standalone application controller and explicit engine ports.

The shell has four primary destinations: workspace, projects, templates and
assets. The shared header has no creation button; creation remains available
through the dashboard composer, page actions and the mobile navigation drawer.
Settings and the product homepage are
reachable through secondary controls, including the mobile navigation drawer.
The dashboard and `/create` both render `components/create-composer.tsx`;
`/create` starts with advanced parameters expanded inline. The dashboard retains
its compact Ant Card and toolbar; its advanced-parameter Button opens an Ant
Drawer and summarizes the current language, page count and style. The drawer
keeps fields mounted, preserves their values and returns focus when closed;
validation opens it before focusing a hidden required field. The composer owns the single
set of defaults, validation, file limits and submission behavior. The dashboard
reads the existing authenticated `/create` HTML for its account-specific settings
and catalogue; it parses only the page JSON, verifies the account/role and never
executes fetched scripts. Failure offers retry instead of submitting incomplete
defaults. Creation reuses the existing backend endpoints.

Quick-mode creation can browse published template packages in a read-only
picker. It reuses the package catalogue, hiding management actions and draft
versions. Selecting a version only updates the creation draft and SVG mode;
it never creates a project. Regular templates remain a design choice after
the outline. Shared template details show the original preview, previous/next
layout controls and a window of up to six thumbnails. Regular project template
selection can return from the preview with a selection without starting work;
the existing explicit generation actions keep their request contracts.

An account/role-keyed, memory-only creation provider retains fields, File objects,
error recovery and the submission lock during client navigation. Full page
reloads discard this draft, as do logout and account/role changes. IME composition
does not submit; errors in collapsed parameters reopen them before focus moves.
Project cards share an Ant Image first-page cover with a stable 16:9 title
fallback during loading, for drafts and after errors. Images load lazily and
the original list remains available through the view toggle. Cards never load
slide documents or iframes. The server summary adds a `cover_url` derived from
the first saved page, without starting any render during listing.

`GET /api/projects/{id}/cover?v={content-hash}` requires the current owner on
every request, including cached images and conditional responses. It renders
the saved 1280x720 page into a 640x360 WebP in an isolated Chromium context,
reusing the existing browser lifecycle. No session credentials are forwarded.
Only bundled static files, the owner's image artifacts and bounded public
resources are available; private network addresses, file URLs, arbitrary API
calls and navigation are blocked. HTML and SVG are supported without AI calls.

Private cache files live in `data/project-covers`, outside static/temp mounts,
scoped by owner, project and first-page content hash. First-page changes invalidate
the URL; outdated URLs return 409, and content/ownership is checked again after
rendering. Renaming or changing later pages reuses the cover. Cache writes are
atomic, older versions retire on successful replacement, and opportunistic
cleanup expires files after 24 hours with a 256 MiB target. Rendering coalesces
identical requests, allows two simultaneous jobs and up to sixteen pending jobs
per web process, and has a 20-second render / 30-second response limit. Failures
cool down for 60 seconds and silently retain the title cover until a later visit.
Browser caches must revalidate; ETags include image bytes so refreshing external
assets can update an otherwise unchanged page. External resources are best effort;
historical decks without individual saved pages continue using title covers.

Regression coverage is in `tests/test_antd_creation_workspace_ui.py` and
`tests/test_antd_creation_templates_ui.py`, with cover regressions in
`tests/test_antd_project_covers_ui.py` and `tests/test_project_covers.py`, alongside
the existing navigation, creation, project, search and pagination suites.

Home is a dedicated product showcase, separate from `/dashboard`. Its editorial
layout uses black actions, a warm paper background, three keyboard-accessible
design examples, the creation workflow and editing/narration/export capabilities.
The examples are local illustrations, labelled as design examples; switching
them never generates a presentation or calls AI. The home-specific shell classes
are removed when leaving the page. Local fonts and SVG/CSS artwork keep it free
of image/CDN requests, and reduced-motion settings disable the sample transition.
The root opens `/home`; the home route no longer queries projects or provider
configuration. Existing authentication and login-to-workspace behavior remain
intact. Creation and workspace actions use their existing routes and permissions.
Responsive layout, example switching, keyboard controls, navigation and routing
coverage live in `tests/test_antd_home_ui.py` and `tests/test_home_routes.py`.
The generation workspace subscribes directly to its independent TypeScript
controller (`src/controllers/generator-controller.ts`). Ant buttons call explicit
actions; no hidden control/status DOM or MutationObserver carries business state.
React Skeleton components show pending outline pages beside generated previews. The
grid retains empty columns and caps desktop previews at 440px, so a single page
does not expand across the workspace. Skeletons follow page numbers, stop their
animation when paused or disconnected, and disappear on completion or failure.
Only six pending placeholders are mounted; unknown totals never invent a page
count or estimated progress. Snapshots expose real stream totals/completed counts,
active page numbers and saved documents. React renders saved and pending pages
with native Ant Card/Tag/Skeleton components. The old Jinja document surface,
fullscreen overlay, global renderer and generator-specific legacy CSS are removed.
Presentation HTML is passed unchanged to iframe srcDoc; it never enters the
application DOM. Stable previews are retained; a replacement updates its own page and an edited
document rejects stale replay. Task records report actual page numbers when
pages finish out of order, using aggregate counts when only counts are known.

Start/pause/resume, stop confirmation, completion and partial retry retain their
API routes. The controller locks concurrent actions, serializes cancellation
before clear-cancel, and checks HTTP/application errors. Failed cancellation
explains that the server may still run; failed clear-cancel remains paused and
never creates an SSE. Terminal events close the source/timers and ignore late
callbacks. Reconnect uses bounded exponential delay and rejects stale sources.
Failed placeholders and duplicate page numbers do not count as a complete deck.
Active unattended runs reject all manual generation actions; only the monitor
may cancel that pipeline. A known running task reads results without starting work.

Pagehide/unmount closes connections, aborts controller reads and clears timers without
sending a cancellation POST. A cached pageshow restores via readonly project GETs,
never automatically replaying stream GET, template preparation or clear-cancel:
the existing stream endpoint can initiate generation. Recovery reads every ten
seconds for up to thirty minutes, with a fifteen-second request timeout; access
loss stops polling and disables restart. Hidden tabs pause recovery polling while
continuing a live stream. Full-document initial loads preserve existing explicit
auto_start and partial-deck continuation, except during known background runs.
Template preparation now has its own controller and native Ant view, described
below. The editor now has its own application controller and established engine ports.
`frontend/tests/generator-controller.test.mjs` exercises state/transport races;
`tests/test_antd_generator_lifecycle_ui.py` covers the built Ant behavior.

The generator's fullscreen view uses Ant Modal with previous/next buttons and
the received-document count. Navigation follows actual saved page numbers,
including gaps; pending pages are not represented as completed documents.
Arrow keys and Escape also work inside same-origin slide frames. Arrow keys
retain their normal behavior in editable fields; if a slide navigates away from
this origin, use the surrounding modal's controls. Closing restores the preview
button's focus, unmounts the document and removes its listeners. Pagehide closes
the preview without a generation or cancellation request.
The shared `SlideDocument` also renders template previews: a ref-owned
ResizeObserver scales the original 1280×720 canvas, with cleanup on unmount.
Fullscreen frames stay interactive. Existing trusted-document execution is
preserved; this migration does not add HTML sanitization or change sandbox policy.
Desktop scrolls the preview grid; phones and short windows scroll the document.
`tests/test_antd_generator_documents_ui.py` covers frame identity, text safety,
partial-deck paging, interactive-frame keys, focus, updates and pagehide cleanup.

The free-template wizard uses Ant Modal, Tabs, Form, Checkbox, Input, Alert and
buttons directly. `src/controllers/template-wizard-controller.ts` owns its
preparation gate, requests, preview/source drafts and confirmation promise. No
Bootstrap modal events, native form relocation, global wizard variables or DOM
observers carry its state. Package and confirmed free modes retain their existing
preparation rules; other projects require an explicitly selected global template.
Failed mode/permission reads never silently authorize generation.

Saved unconfirmed templates are reused. Missing templates generate once after
the user's Start action, using the existing streaming POST (`force`, `stream`,
Accept SSE). Automatic mutation retries are removed: closing/losing a stream
stops reception, keeps drafts and offers a readonly result check. A reported
background generation disables confirmation and avoids duplicate POSTs. Explicit
regeneration warns when the previous result is uncertain or source edits would
be replaced. Fetch/JSON reading each have fifteen-second limits, extended to
five minutes for AI adjustment; the template stream has a two-minute idle limit. Abort signals,
readers, confirmation dialogs and late responses belong to the current operation.

Preview application is local; confirmation submits current source even when it
has not been applied to the preview, along with library/name fields. AI adjustment
retains `adjustment_request` and warns before replacing local source because it
uses the server's saved template. Explicit rejection preserves fields and enables
retry; ambiguous confirmation requires checking saved HTML/confirmation/library
facts. Verified success can continue without another library write. These routes
do not provide operation IDs or guaranteed server cancellation.

Drafts and library fields survive cancel/reopen within this project document;
full navigation/reload discards that memory. Modal contents are destroyed after
close, releasing ResizeObservers and CodeMirror instances; reopening reconstructs
the editor from the draft. Existing pinned CodeMirror is an optional enhancement
with its original options. Ant TextArea remains editable if the CDN is unavailable.
Preview/fullscreen keep the original HTML and 1280x720 canvas. Mobile confirmation
stays outside the scrolling body, with 44px controls. Runtime regressions are in
`frontend/tests/template-wizard-controller.test.mjs` and built-browser checks in
`tests/test_antd_template_wizard_ui.py`. The former native-string tests now exercise
actual page actions and requests.

The PPT editor remains a standalone workspace. `controllers/editor-controller.ts`
owns application subscriptions, saving, document-panel feedback and command errors.
`projectSlidesEditor.engine.js` exposes an explicit command allowlist and snapshots
from the established editing engines. The hidden native header and toolbar have
been removed: Ant view/save/AI/playback/package actions no longer click them or
infer capabilities from their visibility. Core mutation hooks are installed once
and restored when the last subscriber leaves. Document-pane state is sent directly
to the controller, while local DOM attributes remain available for pane layout.
Pagehide releases engine/surface/layout subscriptions; cached pageshow reacquires
them without replaying a request. In-flight writes already started by an engine
are allowed to finish; this lifecycle does not claim to cancel server work.
Repeated Save shares one operation, including native shortcut entry. Saving HTML
now writes only the current page, rather than marking/writing every neighbor.
Failure retains the source and allows deliberate retry.
Ant controls own the header, view modes, save/export/regenerate menus and AI drawer;
thumbnail, CodeMirror, quick-edit, SVG and export engines retain data ownership.
The native surface adapter is limited to specialized dialogs, task messages,
context menus and thumbnail accessibility. It no longer reads business state or
document-panel flags from the DOM. Its delegated keyboard listener is removed
with its observer; the Quick AI icon layout callback uses the explicit engine port.
`frontend/tests/editor-controller.test.mjs` verifies state, save races and lifecycle;
`tests/test_antd_editor_lifecycle_ui.py` covers the built workspace and current-page writes.
A ResizeObserver
invokes the original frame-sizing functions when the new toolbar changes size.
The editor deliberately omits the creation-stage Steps. Project detail, planning
and generation pages retain that navigation; the editor keeps its page counter,
return link and task-specific save/export feedback.
The left sidebar now switches between slides, outline and speech. Text is loaded
on demand, with a page picker, reading/editing modes, fixed save footer and
Chinese/English speech drafts. Drafts remain in this editor session across page,
tab and language switches; leaving the page with unsaved text triggers the browser
warning. The toolbar Save and Ctrl/Cmd+S inside the sidebar save the active text.
Manual speech creation uses no AI; the existing generation/settings and complete
preview dialogs are accessible from the speech pane. Authenticated GET/PATCH
`/api/projects/{id}/editor-documents/{index}` endpoints require ownership and use
page identity, content hashes and transactional project compare-and-swap to reject
stale writes. Outline patches preserve unknown fields, other pages, workflow
metadata, HTML/SVG and canvas edit flags. Speech edits retain generation settings
and isolate each language. Native insertion/deletion/sorting now remap speech and
audio cache indices, with temporary positions avoiding unique cache collisions;
copies receive new page IDs. Failed loads/saves retain drafts and expose retry;
reloading dirty text requires explicit discard. Mobile panes use the existing
sidebar overlay and 44px controls. Regression coverage is in
`tests/test_antd_editor_documents_ui.py` and `tests/test_editor_document_service.py`.
Thumbnail context actions use a grouped Ant menu with the target page title,
clipboard availability and a separate destructive action. The original nine
handlers still perform edits, copy/paste, insertion, duplication and exports.
The menu measures its size and stays inside the viewport, scrolls in short
windows, and closes when scrolling the thumbnail pane or resizing. Shift+F10
and the context-menu key open it; arrows skip disabled items, Escape/Tab return
focus, and cancelling a confirmation restores the target thumbnail. Presentation
artwork, selection and native operation guards remain unchanged.
An editor-only adapter mounts original dialog nodes into Ant frames, keeping
body-child removal, listeners, form values and asynchronous footer insertion.
Once the adapter is mounted, speech preview/settings shells are staged invisibly
until their original content moves inside the Ant frame. They remain measurable
to the bridge, including when React commits late; the legacy body/backdrop never
paints before the modern dialog. Without React, the original preview stays visible.
Frame-level handoff/reopen/fallback coverage is in
`tests/test_antd_speech_dialog_mount_ui.py`.
Native chat, SVG and editor package dialogs use nonmodal `show()` inside those
frames, retaining their close events and SVG dirty-state confirmation. Their
existing `showModal()` behavior remains the fallback outside this workspace.
Nested dialogs keep focus, fixed action footers and ordered overlays; export
progress keeps its existing cancellation availability. Ordinary buttons, text fields, checkboxes and selects now use Ant controls,
forwarding native values, validation, shortcuts and submit events. Scoped styles
align specialized canvas controls with black actions and neutral surfaces.
Quick element controls retain native buttons, color pickers and editing handlers,
with local Ant SVG icons and explicit pressed states. Normal, hover, selected,
disabled and focus styles use the same neutral theme. The draggable AI surface
keeps resize/minimize preferences, expands its input instead of leaving blank
space, and fits its minimum height to visible controls so old sizes cannot clip
Apply. It follows toolbar/viewport bounds and respects reduced motion. Escape
closes it locally, retains the selection/draft and returns focus to its trigger.
PPTX client and SVG conversion use a dedicated Ant dialog with file context,
native stage messages, page counts and live progress. Missing progress remains
indeterminate; the UI adds no timer estimates. The original cancel button and
AbortController own cancellation, including its disabled cleanup state. Escape
and the backdrop keep active tasks open; failure exposes close, Escape and
backdrop dismissal through the original failure handler. Reopening captures a
fresh focus origin. The exporter, speaker notes, downloads and API contracts
remain native; renderer tests isolate the external conversion library.
Sharing uses a dedicated Ant dialog with separate presentation/narration link
cards and copy/open icons beside read-only URLs. Narration appears only when
the original controller provides a link. Native generation, clipboard fallback,
new-window and disable handlers remain responsible for their requests; failed
disable retains the dialog. Closing restores toolbar focus and removes the
native Escape listener. The generation notice is dismissed when the request
finishes; the enabled status in the dialog replaces a second success toast.
Native control adapters also mirror `hidden`/`d-none` classes and restore their
source-hiding class after controller class replacements. Speech preview and edit
modes therefore show exactly one body/textarea, while preserving unsaved values
and the existing save requests. Speech, narration audio and video tasks share
compact black progress cards with stable task names and real stage messages.
Cards appear inside an open speech preview; closing it moves ongoing tasks to
the workspace notification area without duplicating progress or cancelling jobs.
Video export always removes its progress card on success, request failure or
task failure. SSE, polling fallback, payloads and download handling remain native.
Share, template, image, speech/narration, hash/revision and permission-dependent
actions keep their original contracts. Iframe documents and generated SVG are
not restyled. Specialized native surfaces and original form nodes are explicit
compatibility boundaries; CodeMirror, SVG, file selectors and document-editing
engines retain ownership. They are not another application state owner.

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

The task board sends the existing multipart confirmation fields for manual,
file and URL sources. Failed confirmation keeps inputs and files; success removes
the form before starting exactly one existing outline stream. Published package
selection loads on demand, supports retry and uses SVG. Custom audience/style,
page ranges, transition pages and footer controls keep their form names.
The outline list, detailed view, JSON preview/export, JSON and single-slide
editors, regeneration dialog and AI optimization now use Ant components. AI
results remain editable drafts until explicitly saved; failed requests retain
inputs. Single-slide editing preserves unknown fields and optional-field deletion.
Planning now creates a page-scoped `createOutlineController`. It owns snapshots,
SSE parsing, regeneration, cancellation of reception and persisted-result recovery;
it has no React, DOM or global-page dependencies. The Jinja payload provides only
the saved outline, language and stage/confirmation facts, without serializing all
presentation pages into inline JavaScript. The hidden legacy host, generated old
forms/views/dialogs/animations, obsolete CSS and `outline_ui_bridge.js` are removed.
Ant components subscribe directly, and keep existing request, editing and explicit
save contracts. Generation and its template wizard have independent controllers
and native Ant views. Document/fullscreen rendering is React-owned; the deep
PPT editor uses its independent workspace controller and established editing engines.

The planning stage links to `/projects/{id}/todo?view=planning`, so saved outlines
remain accessible after pages exist. The default `/todo` keeps its existing
automatic workspace selection. A known background generation makes planning
read-only; a visible Ant notice explains the lock. Completed projects explain
that outline edits do not automatically change existing pages, with editor access
through the delivery stage. These notices remain visible on phones.

Mount/unmount owns listeners, timers, readers and abort signals. Leaving the page
stops reception/polling; returning through the browser page cache reads
saved results without starting a second generation and retains partial stream text.
Background tab visibility pauses stage polling, which uses the original 15-second
interval and error backoff. Completed projects do not issue that unnecessary poll.
Disconnects show an Ant warning while checking for new persisted output every ten
seconds within a thirty-minute window. Read requests have a fifteen-second limit;
loss of access ends recovery. Full canonical outline signatures reject the old
result while accepting changes to points under unchanged titles. Late replies from
disposed or superseded views cannot update state. Stopping reception does not claim
that a server task has been cancelled; no automatic regeneration POST is added.

The separate stream view owns only supplied DOM refs, preserving reading position
and jump-to-latest across runs. It lazily uses the existing Pretext renderer and
falls back to safe plain text. Listeners, animation frames and renderers detach on
unmount, including an import that resolves after disposal. Generated presentations
are unchanged. `npm run test:controllers --prefix frontend` runs the actual
TypeScript with Node's built-in test runner/type stripping (Node 22.12+), also run
by frontend CI. Browser recovery checks are in
`tests/test_antd_outline_lifecycle_ui.py`; `test_todo_board_frontend.py` invokes
the runtime suite instead of inspecting removed template function strings.

Unattended monitoring retains the original five-second polling/backoff,
visibility handling and terminal callbacks. Both workspace views use Ant progress,
collapsed stage details, failure feedback and confirmed cancellation. Missing runs
hide the panel; historical terminal runs do not trigger reloads. The outline-stage
refresh and longer failure read window are retained. Default native hosts still
receive the existing monitor markup; disposal ignores pending replies.

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

Configuration uses compact icon tabs, provider identity/status rows and short
save actions with explicit accessible names. Model controls use `ModelPicker`:
the saved name and search query are separate, so opening/refetching shows the
full list without replacing custom names. Visible fields open on successful
refresh; a late result never focuses an inactive tab. Lists keep virtual scroll,
keyboard selection and free input where the original field allows it. Provider
changes invalidate role lists, including roles that follow the default provider.

Image settings hide the whole detail card when its source or the image service
is disabled. Source switches stay together; active details and provider credentials
share two columns on desktop and stack on narrow screens. Credentials use a compact
accordion that opens the default image provider and follows provider selection.
Closed sections and hidden sources retain their drafts and all original save
fields. Group visibility uses the existing field subscriptions, without rerendering
every settings tab on each keystroke. The configuration form has smaller spacing;
mobile controls keep their 44px targets.

Shell notices and notification polling still use the existing services in their
own DOM containers. Page forms, dialogs and feedback use Ant Design. Settings
cancel pending requests on unmount, retain edits during an initial read, and
prevent concurrent saves. Keyboard focus stays in dialogs and returns to the
trigger after asynchronous tests.

Project lists share one table/mobile-card collection and action controller.
Search submits on Enter or its icon and matches titles, topics and project IDs
across all pages owned by the authenticated user. The trimmed `search` query
persists through pagination, status changes and reloads. Clearing resets the page
while retaining the status filter. The server applies the same search to results
and counts before pagination, retaining existing effective-status handling and
ownership checks. Automatic list refresh pauses while its toolbar has focus.
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

The versioned package workspace and PPTX slot analyser use Ant modal frames
and ordinary form controls, while lazily loading the original draft/conflict/stream
controllers. Dialog roots retain footer ancestry and submit form association;
asynchronous actions, validation and input values remain available for retry.
Desktop workspace retains three panes; narrow screens switch between pages,
preview and AI editing, with the active pane's actions visible without page scroll.
PPTX file pickers and thumbnail/candidate layout remain specialized components.
No generated slide, published manifest or existing project content is restyled.
The original controller nodes and scoped native components are compatibility
boundaries, not unfinished page shells. Screenshots and verification reports
are stored in ignored `artifacts/` directories.

## Design constraints

Keep black primary actions, neutral surfaces, 14px body text, 20px page headings,
32px desktop controls and 44px mobile touch targets. Configuration tabs wrap on
phones; long forms retain a sticky save action. Keep presentation HTML/SVG and
iframe styles outside application styling.

Keep the page inventory and compatibility boundaries above current.
Remove a page's retired CSS and DOM scripts only when its replacement preserves
its actions, permission visibility and browser regressions. Test built assets,
error/empty states and desktop/mobile geometry. Store screenshots in ignored
`artifacts/` folders.

Editor integration and real five-page creation → generation → editing → export/share acceptance are recorded in `artifacts/editor-finish-20261022/README.md`; specialized engines are intentional compatibility boundaries. No commit or release was made.
