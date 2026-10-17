<!--
  EV icon set (CLAUDE.md §6.3): drawn for EV on a 20 px grid, 1.5 px stroke,
  round caps and joins. Decorative by default; give a label when an icon is
  the only content of a control's accessible name.
-->
<script lang="ts">
  import { PATHS, type IconName } from "./paths";

  interface Props {
    name: IconName;
    size?: number;
  }

  const { name, size = 20 }: Props = $props();
</script>

<svg
  class="icon"
  width={size}
  height={size}
  viewBox="0 0 20 20"
  fill="none"
  stroke="currentColor"
  stroke-width="1.5"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#each PATHS[name] as d (d)}<path {d} />{/each}
</svg>

<style>
  .icon {
    display: block;
    flex-shrink: 0;
  }
</style>
