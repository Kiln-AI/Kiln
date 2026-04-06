#!/usr/bin/env bash

kiln_claude_sandbox_name() {
  printf 'claude-%s\n' "$(basename "$PWD")"
}
