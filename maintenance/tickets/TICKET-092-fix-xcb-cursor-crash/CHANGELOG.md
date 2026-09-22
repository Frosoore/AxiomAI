# CHANGELOG — TICKET-092-fix-xcb-cursor-crash

## [2026-07-01]
- Created ticket documentation and plan.
- Implemented system GUI library validation in [debug/startup_check.py](file:///home/frosoore/AxiomAI/debug/startup_check.py) to check for `libxcb-cursor.so.0` on Linux before initializing `QApplication`.
- Added clear package installation commands for Debian/Ubuntu/Mint, Fedora/RHEL, and Arch/Manjaro to the warning messages.
- Updated [run.sh](file:///home/frosoore/AxiomAI/run.sh) pre-check warning to display the exact distro package install command lines.
- Updated [tools/diagnostic.py](file:///home/frosoore/AxiomAI/tools/diagnostic.py) to include `libxcb-cursor0` presence in the Environment section of diagnostic report, showing FAIL status if it is missing.
- Verified correct behavior using isolated terminal executions under both default and offscreen platform configurations.

## [2026-09-22] — reprise QA (Claude)
- Défaut trouvé à l'audit : le check faisait `sys.exit(1)` dès que la lib manquait, **y compris sous
  Wayland**, où Qt 6 charge son plugin `wayland` et n'a pas besoin de `libxcb-cursor` → lancement
  bloqué à tort. Le message « required under X11/Wayland » était faux.
- `debug/startup_check.py` : nouveau `_uses_xcb(qpa)` (QT_QPA_PLATFORM explicite, 1ʳᵉ entrée d'une
  liste `a;b` ; sinon `WAYLAND_DISPLAY`/`XDG_SESSION_TYPE=wayland` → wayland). Lib absente + Wayland →
  WARNING et lancement autorisé ; lib absente + xcb → FAIL comme avant.
- `tools/diagnostic.py` : WARN au lieu de FAIL sous Wayland.
- Vérifié : `_uses_xcb` sur 4 configurations d'environnement ; `startup_check` OK sur la machine
  (Wayland) ; tests diagnostic verts. **Clos sans test sur X11 (décision utilisateur)**.
