# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-24

### Added
- Initial release.
- 9 subcommands: scan, assess, validate-plan, build-registry, generate-action, validate, audit, doctor, state.
- Single-source-of-truth configs: doc-types.yaml and claim-categories.yaml.
- Semantic claim conflict detection with dominant-value heuristic.
- Auto cross-reference detection in registry generation.
- Doctor command with --full content validation mode.
- 64 pytest tests covering every subcommand.
