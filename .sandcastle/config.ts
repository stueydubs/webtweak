// Sandcastle project config - read by sandcastle-kit (https://github.com/henkisdabro/sandcastle-kit).
// Only what differs from the kit's defaults belongs here.

export default {
  name: "webtweak",
  // baseBranch: "main",
  // label: "ready-for-agent",
  // concurrency: 4,
  // land: "merge",                         // or "squash": one commit per ticket on the base branch
  // autonomy: 0,                           // 1 asks to re-run conflicted and unblocked tickets; 2 or 3 re-run them

  // Claude Code in the sandbox image follows its "stable" release channel. "latest" follows the
  // faster one; an exact version pins it if a release misbehaves (CLAUDE_CODE_VERSION in the
  // environment overrides this for one command).
  // claudeCode: "latest",                  // or an exact version: "2.1.285"

  // Where tickets live. Unset, the kit reads docs/agents/issue-tracker.md (written by
  // Matt Pocock's /setup-matt-pocock-skills, if you ran it) and otherwise uses GitHub.
  // tracker: "github",
  // tracker: "files",                      // .scratch/<feature>/issues/NN-<slug>.md, `Status:` line
  // tracker: { type: "files", dir: "tickets", done: ["done", "shipped"] },
  // Extra things a ticket may wait for: Linear issues, ticket files. README -> Blockers.
  // blockers: { linear: ["ENG"] },

  dockerfile: ".sandcastle/Dockerfile",

  // webtweak has zero runtime dependencies and no package scripts, so there is nothing to install.
  // The Python tools (pytest, playwright) and Chromium live in the image. The gates are the two
  // jobs in .github/workflows/tests.yml; browser tests are selected by marker, never by filename.
  setup: [],
  gates: [
    { name: "stdlib", command: 'python -m pytest -q -m "not browser"' },
    { name: "browser", command: "python -m pytest -q -m browser" },
  ],

  // Vendored third-party code, CI and the Pages deploy. A branch that changes any of these is
  // held for a person instead of merging automatically.
  protectedPaths: ["overlay/interact.min.js", ".github/workflows", "site"],

  // Committed files a command writes. A merge conflict only in these is resolved by taking
  // either side and running `regen` in a sandbox. README -> A gate for generated files.
  // generated: [{ paths: ["dist/site.css"], regen: "pnpm run build:css" }],

  rules: ".sandcastle/rules.md",

  // Models and effort differ from the kit's defaults only when set here, per agent.
  // IMPL_* / REVIEW_* env vars still override them for one run. Repair uses implement's.
  // review: { model: "claude-opus-5-5", effort: "medium" },

  // A red gate gets this many repair passes, fed its output. 0 turns it off.
  // repair: { attempts: 1 },

  // Proof that each kept PreToolUse guard blocks what it should: a made-up tool
  // call handed to the matching hooks in the base-gate sandbox (no model call).
  // hookTests: [
  //   { name: "guard refuses X", tool: "Write", input: { file_path: "a", content: "b" }, expect: "block" },
  // ],

  // Sandboxes load NONE of the repo's skills, agents, commands, MCP servers or
  // plugins unless kept here. Keep only what a run literally needs (e.g. a
  // skill rules.md tells agents to use). Every hook is KEPT - they enforce the
  // repo's rules; dropHooks removes host-only conveniences by a substring of
  // their command, each with a comment saying why. `sandcastle lean` checks both.
  lean: {
    keep: [],
    dropHooks: [
      // "rtk hook claude", // host-only token compressor; not in the image
    ],
  },
};
