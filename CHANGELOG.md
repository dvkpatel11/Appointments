# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Multi-user client management with approval workflow
- Telegram bot webhook integration for chat ID auto-discovery
- Screenshot serving for client status pages
- Application log viewing and downloading
- Global notification settings with persistence
- Docker containerization with Playwright Python base
- Google Cloud Build pipeline for Cloud Run deployment
- Render.com deployment blueprint
- Health check endpoint (`/health`)
- Backup script for JSON state files

### Changed
- Migrated from hardcoded `creds.py` to `.env` configuration (Canada module)
- Dockerfile: added non-root user, HEALTHCHECK, proper dependency installation
- `.gitignore`: expanded to cover runtime state, PII, and tooling artifacts

### Fixed
- *(pending)* Duplicate `except` block in UK module
- *(pending)* UK module using Canadian URLs and Vancouver addresses

### Security
- *(pending)* Add CSRF protection to all POST endpoints
- *(pending)* Add rate limiting on login endpoint
- *(pending)* Add input validation / path traversal protection
- *(pending)* Remove plaintext credential storage in client_tokens.json

### Removed
- *(pending)* Dead commented-out code blocks
