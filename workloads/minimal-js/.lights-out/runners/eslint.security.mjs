// SPDX-License-Identifier: Apache-2.0
//
// The flat config sast.sh runs eslint with (docs/adr/0042 §6): the
// security plugin's recommended rules over every .js, .mjs and .cjs file
// the CLI is pointed at, nothing else -- style is not a gate. Copied into
// the tools' prefix at run time so `eslint-plugin-security` resolves from
// there, not from the repository.
import security from "eslint-plugin-security";

export default [
  {
    ...security.configs.recommended,
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        console: "readonly",
        process: "readonly",
        require: "readonly",
        module: "writable",
        __dirname: "readonly",
      },
    },
  },
];
