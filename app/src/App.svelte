<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";

  import Island from "./lib/island/Island.svelte";
  import Settings from "./lib/settings/Settings.svelte";

  // One bundle serves both windows; the window label picks the view.
  const label = getCurrentWindow().label;
</script>

{#if label === "settings"}
  <Settings />
{:else}
  <Island />
{/if}
