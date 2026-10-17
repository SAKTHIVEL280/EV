import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";

// Design rule (CLAUDE.md §6.3): tokens are the only source of visual values.
// Components may not contain raw colors; tokens live in src/lib/tokens/.
const rawColor = {
  selector: "Literal[value=/#[0-9a-fA-F]{3,8}\\b|rgba?\\(|hsla?\\(/]",
  message: "Use a design token (src/lib/tokens) instead of a raw color.",
};

export default ts.config(
  { ignores: ["dist/", "src-tauri/", "src/lib/bindings.ts", "node_modules/"] },
  js.configs.recommended,
  ...ts.configs.strictTypeChecked,
  ...svelte.configs["flat/recommended"],
  {
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: true,
        extraFileExtensions: [".svelte"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "no-restricted-syntax": ["error", rawColor],
    },
  },
  {
    files: ["**/*.svelte", "**/*.svelte.ts"],
    languageOptions: { parserOptions: { parser: ts.parser } },
  },
  {
    files: ["*.config.js", "*.config.ts"],
    ...ts.configs.disableTypeChecked,
  },
);
