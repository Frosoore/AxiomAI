# CHANGELOG — TICKET-092-fix-xcb-cursor-crash

## [2026-07-01]
- Created ticket documentation and plan.
- Implemented system GUI library validation in [debug/startup_check.py](file:///home/frosoore/AxiomAI/debug/startup_check.py) to check for `libxcb-cursor.so.0` on Linux before initializing `QApplication`.
- Added clear package installation commands for Debian/Ubuntu/Mint, Fedora/RHEL, and Arch/Manjaro to the warning messages.
- Updated [run.sh](file:///home/frosoore/AxiomAI/run.sh) pre-check warning to display the exact distro package install command lines.
- Updated [tools/diagnostic.py](file:///home/frosoore/AxiomAI/tools/diagnostic.py) to include `libxcb-cursor0` presence in the Environment section of diagnostic report, showing FAIL status if it is missing.
- Verified correct behavior using isolated terminal executions under both default and offscreen platform configurations.
