<!--
  Settings window (docs/FEATURES.md F-410, CLAUDE.md §6.5): left navigation,
  right content. Every change applies at once through core; there is no Save.
-->
<script lang="ts">
  import { getVersion } from "@tauri-apps/api/app";
  import { onMount, tick } from "svelte";

  import {
    commands,
    events,
    type CoreStatus,
    type HotkeyStatus,
    type SettingItem,
    type SettingsState,
    type SettingValue,
  } from "../bindings";
  import {
    SECTIONS,
    displayValue,
    groupsFor,
    isDefault,
    itemId,
    itemsFor,
    sectionById,
    type SectionId,
  } from "./settings";
  import ModelList from "../models/ModelList.svelte";
  import { models } from "../models/store.svelte";
  import ArcPreview from "./ArcPreview.svelte";
  import { shortcutLabel } from "./controls";
  import SettingControl from "./SettingControl.svelte";

  let settings = $state<SettingsState | null>(null);
  let core = $state<CoreStatus>({ state: "starting" });
  let current = $state<SectionId>("general");
  let errors = $state<Record<string, string>>({});
  let appVersion = $state("");
  let hotkey = $state<HotkeyStatus | null>(null);

  const hotkeyText = $derived.by(() => {
    if (!hotkey) return null;
    const base =
      hotkey.state === "active"
        ? `${shortcutLabel(hotkey.shortcut)} is active.`
        : hotkey.state === "off"
          ? "No shortcut is set."
          : (hotkey.detail ?? "This shortcut can't be used.");
    return hotkey.state === "active" && hotkey.detail ? `${base} ${hotkey.detail}` : base;
  });

  const section = $derived(sectionById(current));
  const items = $derived(itemsFor(settings, current));
  const groups = $derived(groupsFor(items));
  const arcWidth = $derived(items.find((i) => i.section === "island" && i.key === "arc_width"));
  const arcDepth = $derived(items.find((i) => i.section === "island" && i.key === "arc_depth"));
  const coreUp = $derived(core.state === "running");
  const modules = $derived(core.state === "running" ? core.modules : []);

  function setError(item: SettingItem, message: string | null): void {
    const id = itemId(item);
    const rest = Object.fromEntries(Object.entries(errors).filter(([key]) => key !== id));
    errors = message === null ? rest : { ...rest, [id]: message };
  }

  async function apply(item: SettingItem, value: SettingValue): Promise<void> {
    setError(item, null);
    const result = await commands.settingsSet(item.section, item.key, value);
    if (result.status === "error") setError(item, result.error.message);
  }

  async function reset(item: SettingItem): Promise<void> {
    setError(item, null);
    const result = await commands.settingsReset(item.section, item.key);
    if (result.status === "error") setError(item, result.error.message);
  }

  async function openFile(which: "config" | "logs"): Promise<void> {
    const result =
      which === "config" ? await commands.openConfigFile() : await commands.openLogsFolder();
    if (result.status === "error") errors = { ...errors, [which]: result.error.message };
  }

  // Smoke test (CI): report once core's settings are on screen.
  let smokeTest = $state(false);
  let smokeReported = false;
  $effect(() => {
    if (!smokeTest || smokeReported || !settings || settings.items.length === 0) return;
    smokeReported = true;
    void tick().then(() => commands.smokeTestStep("settings-rendered"));
  });

  onMount(() => {
    models.init();
    void commands.smokeTestMode().then((enabled) => {
      smokeTest = enabled;
    });
    const unlisteners = [
      events.settingsChanged.listen((event) => {
        settings = event.payload;
        errors = {};
      }),
      events.settingRejected.listen((event) => {
        const { section: s, key, message } = event.payload;
        errors = { ...errors, [`${s}.${key}`]: message };
      }),
      events.hotkeyStatusChanged.listen((event) => {
        hotkey = event.payload;
      }),
      events.coreStatusChanged.listen((event) => {
        core = event.payload;
        if (event.payload.state === "running") void commands.settingsRefresh();
      }),
    ];
    void commands.settingsState().then((cached) => {
      if (cached) settings = cached;
    });
    void commands.coreStatus().then((status) => {
      core = status;
    });
    void commands.settingsRefresh();
    void commands.hotkeyStatus().then((status) => {
      hotkey = status;
    });
    void getVersion().then((version) => {
      appVersion = version;
    });
    return () => {
      for (const pending of unlisteners)
        void pending.then((unlisten) => {
          unlisten();
        });
    };
  });
</script>

<div class="settings">
  <nav aria-label="Settings sections">
    <ul>
      {#each SECTIONS as entry (entry.id)}
        <li>
          <button
            type="button"
            aria-current={entry.id === current ? "page" : undefined}
            onclick={() => (current = entry.id)}
          >
            {entry.label}
          </button>
        </li>
      {/each}
    </ul>
  </nav>

  <main>
    <header class="page">
      <h1>{section.label}</h1>
      <p class="summary">{section.summary}</p>
    </header>

    {#if !coreUp}
      <p class="notice" role="status">EV's core isn't running. Settings can't be changed now.</p>
    {/if}

    {#if current === "models"}
      <section class="block">
        <h2>Models</h2>
        <p class="description">
          Models run on this PC. Downloads come from Hugging Face and are checked before use.
        </p>
        <ModelList variant="settings" />
        {#if models.state}<p class="path">{models.state.models_dir}</p>{/if}
      </section>
    {/if}

    {#if current === "appearance" && arcWidth && arcDepth}
      <ArcPreview
        width={arcWidth}
        depth={arcDepth}
        disabled={!coreUp}
        apply={(item: SettingItem, value: SettingValue) => void apply(item, value)}
      />
    {/if}

    {#if items.length > 0}
      {#each groups as group (group.title)}
        <section class="group" aria-labelledby={`group-${group.title}`}>
          {#if groups.length > 1}<h2 id={`group-${group.title}`}>{group.title}</h2>{/if}
          <ul class="items">
            {#each group.items as item (itemId(item))}
              <li class="item">
                <div class="text">
                  <span class="label" id={`label-${itemId(item)}`}>{item.label}</span>
                  <span class="description">{item.description}</span>
                  {#if !isDefault(item)}
                    <span class="default">Default: {displayValue(item, item.default)}</span>
                  {/if}
                </div>
                <div class="control">
                  <SettingControl
                    {item}
                    disabled={!coreUp}
                    apply={(value: SettingValue) => void apply(item, value)}
                    fail={(message: string | null) => {
                      setError(item, message);
                    }}
                    showModels={() => (current = "models")}
                  />
                  {#if !isDefault(item)}
                    <button
                      type="button"
                      class="link"
                      disabled={!coreUp}
                      onclick={() => void reset(item)}
                    >
                      Reset
                    </button>
                  {/if}
                </div>
                {#if errors[itemId(item)]}
                  <p class="error" role="alert">{errors[itemId(item)]}</p>
                {/if}
              </li>
            {/each}
          </ul>
        </section>
      {/each}
    {:else if section.empty}
      <p class="empty">{section.empty}</p>
    {/if}

    {#if current === "hotkeys" && hotkeyText}
      <p class="status-line" role="status">{hotkeyText}</p>
    {/if}

    {#if current === "advanced"}
      <section class="block">
        <h2>Config file</h2>
        <p class="description">
          Every setting lives in this file. Edits apply at once; invalid values fall back to their
          defaults and show a warning in Diagnostics.
        </p>
        {#if settings}<p class="path">{settings.path}</p>{/if}
        <button type="button" class="action" onclick={() => void openFile("config")}>
          Open config file
        </button>
        {#if errors["config"]}<p class="error" role="alert">{errors["config"]}</p>{/if}
      </section>
    {/if}

    {#if current === "diagnostics"}
      <section class="block">
        <h2>Modules</h2>
        {#if modules.length === 0}
          <p class="description">No module status yet.</p>
        {:else}
          <ul class="rows">
            {#each modules as module (module.name)}
              <li>
                <span class="label">{module.name}</span>
                <span class="description"
                  >{module.state}{module.detail ? ` · ${module.detail}` : ""}</span
                >
              </li>
            {/each}
          </ul>
        {/if}
      </section>
      <section class="block">
        <h2>Config warnings</h2>
        {#if !settings || settings.warnings.length === 0}
          <p class="description">None.</p>
        {:else}
          <ul class="rows">
            {#each settings.warnings as warning (warning.key + warning.message)}
              <li>
                <span class="label">{warning.key || "config.toml"}</span>
                <span class="description">{warning.message}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
      <section class="block">
        <h2>Logs</h2>
        <button type="button" class="action" onclick={() => void openFile("logs")}>
          Open logs folder
        </button>
        {#if errors["logs"]}<p class="error" role="alert">{errors["logs"]}</p>{/if}
      </section>
    {/if}

    {#if current === "about"}
      <section class="block">
        <ul class="rows">
          <li><span class="label">EV</span><span class="description">{appVersion}</span></li>
          <li>
            <span class="label">Core</span>
            <span class="description"
              >{core.state === "running" ? core.core_version : "not running"}</span
            >
          </li>
          <li><span class="label">License</span><span class="description">Apache-2.0</span></li>
          <li>
            <span class="label">Third-party software</span>
            <span class="description">Listed in THIRD_PARTY_NOTICES.md in the install folder.</span>
          </li>
        </ul>
      </section>
    {/if}
  </main>
</div>

<style>
  .settings {
    --ev-scrollbar-thumb: var(--ev-fg-3);
    --ev-scrollbar-thumb-hover: var(--ev-fg-2);
    --ev-scrollbar-track: var(--ev-hairline);
    position: fixed;
    inset: 0;
    display: grid;
    grid-template-columns: 224px 1fr;
    background: var(--ev-surface);
    color: var(--ev-fg-1);
    font-family: var(--ev-font-sans);
    font-size: var(--ev-text-13);
    user-select: text;
  }

  nav {
    background: var(--ev-surface-nav);
    border-right: 1px solid var(--ev-hairline);
    padding: var(--ev-space-5) var(--ev-space-3);
    overflow-y: auto;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  nav button {
    width: 100%;
    text-align: left;
    font: inherit;
    color: var(--ev-fg-2);
    background: transparent;
    border: 0;
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-3);
    cursor: pointer;
  }

  nav button:hover {
    background: var(--ev-control);
  }

  nav button[aria-current="page"] {
    color: var(--ev-fg-1);
    background: var(--ev-selected);
    font-weight: var(--ev-weight-medium);
  }

  main {
    overflow-y: auto;
    padding: var(--ev-space-5) calc(var(--ev-space-5) * 2);
  }

  .page {
    margin-bottom: var(--ev-space-4);
  }

  h1 {
    margin: 0 0 var(--ev-space-1);
    font-size: var(--ev-text-28);
    font-weight: var(--ev-weight-semibold);
    letter-spacing: -0.01em;
  }

  .summary {
    color: var(--ev-fg-2);
    font-size: var(--ev-text-15);
  }

  h2 {
    margin: 0 0 var(--ev-space-2);
    font-size: var(--ev-text-15);
    font-weight: var(--ev-weight-semibold);
  }

  .group {
    margin-top: var(--ev-space-5);
  }

  .group h2 {
    font-size: var(--ev-text-11);
    font-weight: var(--ev-weight-semibold);
    color: var(--ev-fg-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding-bottom: var(--ev-space-2);
    border-bottom: 1px solid var(--ev-hairline);
    margin: 0;
  }

  p {
    margin: 0;
  }

  .notice,
  .empty {
    color: var(--ev-fg-2);
    margin-bottom: var(--ev-space-4);
  }

  .item {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--ev-space-1) var(--ev-space-5);
    padding: var(--ev-space-4) 0;
    border-bottom: 1px solid var(--ev-hairline);
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: var(--ev-space-1);
  }

  .label {
    font-size: var(--ev-text-15);
    font-weight: var(--ev-weight-medium);
  }

  .description,
  .default,
  .path {
    color: var(--ev-fg-2);
  }

  .default {
    color: var(--ev-fg-3);
    font-size: var(--ev-text-11);
    font-variant-numeric: tabular-nums;
  }

  .path {
    font-family: var(--ev-font-mono);
    font-size: var(--ev-text-11);
    margin: var(--ev-space-2) 0;
    word-break: break-all;
  }

  .control {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--ev-space-2);
  }

  .error {
    grid-column: 1 / -1;
    color: var(--ev-fg-1);
    font-weight: var(--ev-weight-medium);
  }

  .action,
  .link {
    font: inherit;
    color: var(--ev-fg-1);
    border: 0;
    cursor: pointer;
  }

  .action {
    background: var(--ev-control);
    border-radius: var(--ev-radius-control);
    padding: var(--ev-space-2) var(--ev-space-4);
    margin-top: var(--ev-space-2);
  }

  .action:hover {
    background: var(--ev-control-hover);
  }

  .link {
    background: transparent;
    color: var(--ev-fg-2);
    text-decoration: underline;
    padding: 0;
  }

  button:disabled {
    cursor: default;
    opacity: 0.5;
  }

  button:focus-visible {
    outline: 2px solid var(--ev-theme-focus-ring);
    outline-offset: 2px;
  }

  .status-line {
    margin-top: var(--ev-space-4);
    color: var(--ev-fg-2);
  }

  .block {
    padding: var(--ev-space-4) 0;
    border-bottom: 1px solid var(--ev-hairline);
  }

  .rows li {
    display: flex;
    justify-content: space-between;
    gap: var(--ev-space-4);
    padding: var(--ev-space-2) 0;
  }
</style>
